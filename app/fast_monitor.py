"""Fair incremental scheduling. All browser work shares one persistent context."""
from collections import deque
from dataclasses import dataclass
from dataclasses import asdict
import hashlib
import json
from html import escape
from datetime import datetime, timezone
import logging
import time
from urllib.parse import quote_plus, urlsplit

from app.collectors.groups.playwright_client import snapshot, post_from_article
from app.collectors.marketplace.playwright_client import PlaywrightMarketplaceCollector, _matches_query
from app.notifications.telegram import TelegramError, format_listings, send_html
from app.products.normalizer import normalize_group, normalize_marketplace

LOGGER = logging.getLogger(__name__)


class BrowserRecoveryNeeded(RuntimeError):
    """The browser context cannot create a usable replacement page."""


@dataclass
class Job:
    name: str
    interval: float
    due: float = 0
    last_finished: float | None = None


class Scheduler:
    def __init__(self, group_urls, *, marketplace_interval=120, group_interval=300):
        self.jobs = [Job('marketplace', marketplace_interval)]
        self.jobs.extend(Job(url, group_interval) for url in group_urls)
        self.jobs.extend([Job('details', 1), Job('notifications', 30), Job('catchup', 900)])

    def next(self, now):
        ready = [job for job in self.jobs if job.due <= now]
        return min(ready, key=lambda job: job.due) if ready else None

    def finish(self, job, started, finished):
        # Schedule from scan start, not completion; slow jobs cannot silently
        # add their duration to every requested interval.
        job.last_finished = finished
        job.due = max(started + job.interval, finished)


class FastMonitor:
    def __init__(self, context, repository, settings):
        self.context, self.repository, self.settings = context, repository, settings
        self.attach_context(context)
        self.detail_queue = deque()
        self.queued = set()
        self.detail_retry = {}
        self.detail_attempts = {}
        self.discovery_times = {}
        self.group_plain = set()
        self.alert_times = {}
        self.zero_scans = {}
        self.catchup_scrolls = 6

    def attach_context(self, context):
        self.context = context
        self.page_faults = set()
        for name in ('search_page', 'group_page', 'detail_page'):
            self.new_page(name)

    def new_page(self, name):
        try:
            page = self.context.new_page()
            page.on('crash', lambda _: self.page_faults.add(name))
            page.on('close', lambda _: self.page_faults.add(name))
            setattr(self, name, page)
            self.page_faults.discard(name)
        except Exception as error:
            raise BrowserRecoveryNeeded(f'Cannot replace {name}') from error

    def recover_page(self, name):
        old = getattr(self, name)
        try:
            old.close()
        except Exception:
            pass
        self.new_page(name)
        LOGGER.warning('page_recovered page=%s queue=%d', name, len(self.detail_queue))

    @staticmethod
    def fingerprint(item):
        from app.products.text import normalize_text
        return hashlib.sha256(f'{normalize_text(item.title)}|{item.price}'.encode()).hexdigest()

    def retry_detail(self, item, reason):
        old = self.repository.get_detail_task(item.source_id)
        missing_fields = reason.startswith('missing_') and reason != 'missing_item_data'
        same_kind = old and (old['reason'] == reason or
            (not missing_fields and old['state'] in ('transient_retry', 'cooldown')))
        attempts = old['attempts'] + 1 if same_kind else 1
        if reason == 'listing_unavailable':
            state, delay = 'unavailable', 21600
        elif missing_fields and attempts >= 2:
            state, delay = 'awaiting_data', 21600
        elif missing_fields:
            state, delay = 'confirm_missing', 30
        elif attempts >= 3:
            state, delay = 'cooldown', 900
        else:
            state, delay = 'transient_retry', 30 * attempts
        payload = asdict(item)
        if payload['created_at']:
            payload['created_at'] = payload['created_at'].isoformat()
        discovered = self.discovery_times.get(item.source_id, datetime.now(timezone.utc)).isoformat()
        self.repository.defer_detail(source_id=item.source_id, payload=json.dumps(payload), fingerprint=self.fingerprint(item),
            state=state, reason=reason, attempts=attempts, delay_seconds=delay, discovered_at=discovered)
        self.queued.discard(item.source_id)
        self.discovery_times.pop(item.source_id, None)
        LOGGER.warning('detail_deferred id=%s reason=%s state=%s attempts=%d delay=%ds', item.source_id, reason, state, attempts, delay)

    @staticmethod
    def check_login(page):
        if 'login' in page.url or page.locator('input[name="email"]').count():
            raise RuntimeError('Facebook login expired; run marketplace-login')

    def enqueue(self, item, *, refresh=False):
        if item.source_id in self.queued:
            return
        task = self.repository.get_detail_task(item.source_id)
        changed = task and task['fingerprint'] != self.fingerprint(item)
        if task and not changed:
            return  # Delayed tasks are restored by details(), not every search.
        if changed:
            self.discovery_times[item.source_id] = datetime.fromisoformat(task['discovered_at'])
            self.repository.clear_detail_task(item.source_id)
            LOGGER.info('detail_recheck_on_card_change id=%s', item.source_id)
        row = self.repository.get('marketplace', item.source_id)
        if row and not refresh and not changed:
            return
        if row:
            observed = datetime.fromisoformat(row['observed_at']) if row['observed_at'] else None
            if not changed and observed and (datetime.now(timezone.utc)-observed).total_seconds() < 900:
                return
            self.detail_queue.append(item)
        else:
            self.detail_queue.appendleft(item)
            self.discovery_times.setdefault(item.source_id, datetime.now(timezone.utc))
        self.queued.add(item.source_id)

    def marketplace(self, *, catchup=False):
        page = self.search_page
        query = quote_plus('iPhone 17 Pro Max')
        page.goto(f'https://www.facebook.com/marketplace/search/?query={query}&sortBy=creation_time_descend',
                  wait_until='domcontentloaded', timeout=15000)
        self.check_login(page)
        page.wait_for_timeout(1500)
        # URL parameters alone are not proof that Facebook applied the sort.
        labels = page.locator('[role="combobox"], [aria-haspopup="listbox"]').all_text_contents()
        confirmed = any(
            ('Date listed' in label or '刊登日期' in label or '上架日期' in label)
            and ('Newest' in label or '最新' in label or '由新到舊' in label)
            for label in labels
        )
        LOGGER.info('marketplace_sort requested=newest confirmed=%s', confirmed)
        if not confirmed:
            LOGGER.warning('marketplace_sort_unconfirmed coverage_not_guaranteed')
        found = {}
        deadline = time.monotonic() + (25 if catchup else 8)
        for _ in range((self.catchup_scrolls if catchup else 2) + 1):
            PlaywrightMarketplaceCollector._collect_cards(page, found)
            if time.monotonic() >= deadline:
                break
            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(700)
        for item in reversed(list(found.values())):
            if _matches_query(item, 'iPhone 17 Pro Max'):
                self.enqueue(item)
        if catchup:
            # Refresh known items after discovery work. A burst of new items
            # must not be queued behind every previously seen listing.
            for item in found.values():
                if _matches_query(item, 'iPhone 17 Pro Max'):
                    self.enqueue(item, refresh=True)
            self.catchup_scrolls = 6 if self.catchup_scrolls >= 18 else self.catchup_scrolls + 3
        LOGGER.info('scan source=marketplace mode=%s cards=%d queue=%d', 'catchup' if catchup else 'fast', len(found), len(self.detail_queue))

    def details(self):
        from dataclasses import replace
        if not self.detail_queue:
            from app.collectors.marketplace.models import RawMarketplaceListing
            for task in self.repository.due_detail_tasks(5):
                if task['source_id'] in self.queued:
                    continue
                values = json.loads(task['payload'])
                if values.get('created_at'):
                    values['created_at'] = datetime.fromisoformat(values['created_at'])
                self.detail_queue.append(RawMarketplaceListing(**values))
                self.queued.add(task['source_id'])
                self.discovery_times[task['source_id']] = datetime.fromisoformat(task['discovered_at'])
        if not self.detail_queue:
            return
        item = self.detail_queue.popleft()
        self.queued.remove(item.source_id)
        try:
            page = self.detail_page
            page.goto(item.url, wait_until='domcontentloaded', timeout=12000)
            self.check_login(page)
            page.wait_for_timeout(700)
            # Reuse the source-isolated HTML parser without another navigation.
            from app.collectors.marketplace.playwright_client import _listing_data, _creation_time, _location, _text_field
            data = _listing_data(page.content(), item.source_id)
            description = _text_field(data, 'redacted_description')
            if not data:
                unavailable = hasattr(page, 'get_by_text') and any(page.get_by_text(text, exact=True).count() for text in
                    ('此商品已不再提供', '此商品已售出', 'This listing is no longer available', 'This listing has been sold'))
                self.retry_detail(item, 'listing_unavailable' if unavailable else 'missing_item_data')
                return
            # Card prices may be stale; prefer the detail parser's description
            # only when it includes an unambiguous sale price.
            from app.products.price_parser import parse_price
            enriched = replace(item, description=description or item.description,
                               location=_location(data) or item.location,
                               created_at=_creation_time(data), price=parse_price(description or '') or item.price)
            listing = normalize_marketplace(enriched)
            from app.products.matcher import KeywordMatcher
            from app.products.storage_parser import parse_storage_gb
            content = f'{listing.title} {listing.description or ""}'
            missing = []
            if parse_storage_gb(content) is None:
                missing.append('capacity')
            if listing.price is None or listing.price <= 0:
                missing.append('price')
            if not listing.location:
                missing.append('location')
            LOGGER.info('detail_fields id=%s description_present=%s missing=%s post_time_known=%s',
                        item.source_id, bool(description), ','.join(missing) or 'none', listing.created_at is not None)
            if missing and KeywordMatcher(('iPhone 17 Pro Max',)).matches(content):
                # Do not overwrite a previously validated record with an
                # incomplete refresh, or notify with missing required fields.
                self.retry_detail(item, 'missing_' + '_'.join(missing))
                return
            if item.source_id in self.discovery_times:
                listing = replace(listing, first_seen_at=self.discovery_times.pop(item.source_id))
            self.save(listing)
            self.repository.clear_detail_task(item.source_id)
            self.detail_retry.pop(item.source_id, None)
            self.detail_attempts.pop(item.source_id, None)
        except Exception as error:
            self.retry_detail(item, type(error).__name__)
            raise

    def group(self, url):
        page = self.group_page
        plain = url in self.group_plain
        target = url if plain else url.rstrip('/') + '/?sorting_setting=CHRONOLOGICAL'
        page.goto(target, wait_until='domcontentloaded', timeout=12000)
        self.check_login(page)
        deadline = time.monotonic() + 8
        seen = set()
        for step in range(3):
            page.wait_for_timeout(1000)
            for label in ('查看更多', '顯示更多'):
                controls = page.get_by_text(label, exact=True)
                for index in range(min(controls.count(), 3)):
                    if time.monotonic() >= deadline:
                        break
                    try:
                        controls.nth(index).click(timeout=200)
                    except Exception:
                        pass
            for record in snapshot(page):
                post = post_from_article(record['text'], record['href'], timestamp=record['timestamp'],
                    time_label=record['timeLabel'], group_id=urlsplit(url).path.strip('/').split('/')[1])
                if post and post.source_id not in seen:
                    seen.add(post.source_id)
                    self.save(normalize_group(post))
            if time.monotonic() >= deadline:
                break
            page.mouse.wheel(0, 1800)
        if not seen:
            self.zero_scans[url] = self.zero_scans.get(url, 0) + 1
            if self.zero_scans[url] >= 3:
                self.alert('zero:' + url, '群組連續三次未解析到貼文：' + url)
            if plain:
                self.group_plain.discard(url)
            else:
                self.group_plain.add(url)
            LOGGER.warning('group_zero_posts url=%s next_scan_alternate_mode=true', url)
        else:
            self.zero_scans[url] = 0
        LOGGER.info('scan source=group url=%s posts=%d sort=%s', url, len(seen), 'plain_unconfirmed' if plain else 'chronological_requested')

    def save(self, listing):
        result = self.repository.save(listing)
        LOGGER.info('listing source=%s id=%s new=%s rejection=%s', listing.source, listing.source_id, result.is_new, result.rejection_reason)
        if result.is_eligible:
            self.notifications(limit=1, listing_id=self.repository.get(listing.source, listing.source_id)['id'])

    def alert(self, key, message):
        now = time.monotonic()
        if now - self.alert_times.get(key, -100000) < 1800:
            return
        self.alert_times[key] = now
        LOGGER.warning('monitor_alert key=%s', key)
        try:
            send_html(self.settings.telegram_bot_token or '', self.settings.telegram_chat_id or '',
                      '⚠️ 監控異常\n' + escape(message), timeout=5)
        except Exception:
            LOGGER.warning('monitor_alert_delivery_failed key=%s', key)

    def notifications(self, *, limit=1, listing_id=None):
        rows = self.repository.list_recent(None if listing_id else limit, only_unnotified=True, only_eligible=True)
        if listing_id is not None:
            rows = [row for row in rows if row['id'] == listing_id]
        for row in rows:
            try:
                send_html(self.settings.telegram_bot_token or '', self.settings.telegram_chat_id or '', format_listings([row]), timeout=10)
            except Exception as error:
                delay = getattr(error, 'retry_after', None) or 60
                self.repository.mark_notification_failed(row['id'], str(error), retry_after_seconds=delay)
                if isinstance(error, TelegramError) and error.status_code == 429:
                    self.repository.defer_notifications(delay)
                raise
            self.repository.mark_notified(row['id'], sent_price=row['price'])
            now = datetime.now(timezone.utc)
            posted = datetime.fromisoformat(row['last_seen_at']) if row['last_seen_at'] else None
            latency = (now - posted).total_seconds() if posted else None
            discovery_delay = (now-datetime.fromisoformat(row['first_seen_at'])).total_seconds()
            LOGGER.info('notification_sent id=%s publication_delay_seconds=%s discovery_to_send_seconds=%.1f within_10min=%s', row['id'], latency, discovery_delay, latency <= 600 if latency is not None else 'unknown')

    def run(self, scheduler, *, clock=time.monotonic, sleep=time.sleep, duration=14400, should_stop=lambda: False):
        end = clock() + duration
        failures = {}
        reporter = getattr(self, 'status_reporter', None)
        while clock() < end and not should_stop():
            if reporter:
                reporter.pulse()
            now = clock()
            job = scheduler.next(now)
            if job is None:
                sleep(0.5)
                continue
            started = clock()
            retry_soon = False
            outcome = 'success'
            error_type = None
            if reporter:
                reporter.begin(job.name)
            overdue = max(0, started - job.due) if job.due else 0
            if overdue > 60:
                LOGGER.warning('scan_overdue source=%s seconds=%.1f', job.name, overdue)
            if overdue > 120:
                self.alert('overdue:' + job.name, f'掃描落後預定時間 {overdue:.0f} 秒：{job.name}')
            try:
                page_name = ('search_page' if job.name in ('marketplace', 'catchup') else
                             'detail_page' if job.name == 'details' else
                             'group_page' if job.name != 'notifications' else None)
                if page_name and page_name in getattr(self, 'page_faults', set()):
                    self.recover_page(page_name)
                if job.name in ('marketplace', 'catchup'):
                    self.marketplace(catchup=job.name == 'catchup')
                elif job.name == 'details':
                    self.details()
                elif job.name == 'notifications':
                    self.notifications()
                else:
                    self.group(job.name)
                failures[job.name] = 0
            except Exception as error:
                outcome = 'failed'
                error_type = type(error).__name__
                if isinstance(error, BrowserRecoveryNeeded):
                    raise
                failures[job.name] = failures.get(job.name, 0) + 1
                LOGGER.warning('scan_failed source=%s error_type=%s', job.name, type(error).__name__)
                message = str(error)
                closed = type(error).__name__ == 'TargetClosedError' or 'Page crashed' in message or 'Target crashed' in message
                if page_name and (closed or (type(error).__name__ == 'TimeoutError' and failures[job.name] >= 2)):
                    self.recover_page(page_name)
                    # Attempt again soon instead of waiting the full scan interval.
                    retry_soon = True
                if closed:
                    LOGGER.warning('scan_recovery_requested source=%s', job.name)
                elif failures[job.name] >= 3:
                    self.alert('failed:' + job.name, f'{job.name} 連續執行失敗：{type(error).__name__}，請檢查日誌')
            finally:
                if reporter:
                    reporter.finish(job.name, outcome, clock()-started, error_type)
                scheduler.finish(job, started, clock())
                if retry_soon:
                    job.due = min(job.due, clock() + 15)
                LOGGER.info('scan_completed source=%s elapsed=%.1f queue=%d outcome=%s', job.name, clock()-started, len(self.detail_queue), outcome)
