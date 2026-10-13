from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

from app.collectors.marketplace.playwright_client import parse_posted_at
from .models import RawGroupPost


LOGGER = logging.getLogger(__name__)
_POST_URL = re.compile(r"/groups/([^/]+)/(?:posts|permalink)/(\d+)")
_COMMERCE_URL = re.compile(r"/commerce/listing/(\d+)")


def snapshot(page: object) -> list[dict]:
    return page.locator('[role="article"], [data-ad-preview="message"], [data-ad-comet-preview="message"]').evaluate_all("""elements => {
        const postPattern = /\\/groups\\/[^/]+\\/(posts|permalink)\\/\\d+|\\/commerce\\/listing\\/\\d+/;
        const messageSelector = '[data-ad-preview="message"], [data-ad-comet-preview="message"]';
        const candidates = [];
        const seen = new Set();
        const belongsTo = (node, root) => {
            const article = node.closest('[role="article"]');
            return root.matches('[role="article"]') ? article === root : !article;
        };
        for (const element of elements) {
            if (element.matches(messageSelector)) {
                const owner = element.closest('[role="article"]');
                if (owner && owner.parentElement.closest('[role="article"]')) continue;
                let root = element.parentElement;
                for (let depth = 0; root && depth < 15; depth++, root = root.parentElement) {
                    if (root.matches('body, [role="feed"], [role="main"]')) break;
                    const messages = [...root.querySelectorAll(messageSelector)]
                        .filter(message => belongsTo(message, root));
                    if (messages.length > 1) break;
                    if (belongsTo(element, root) && [...root.querySelectorAll('a[href]')].some(a => belongsTo(a, root) && postPattern.test(a.href))) {
                        if (!seen.has(root)) { candidates.push({article: root, body: element}); seen.add(root); }
                        break;
                    }
                }
            }
        }
        for (const element of elements) {
            if (!element.matches('[role="article"]') || element.parentElement.closest('[role="article"]')) continue;
            if (candidates.some(candidate => element.contains(candidate.body))) continue;
            const body = [...element.querySelectorAll(messageSelector)].find(message => belongsTo(message, element));
            if (!seen.has(element)) { candidates.push({article: element, body}); seen.add(element); }
        }
        return candidates.map(({article, body}) => {
        const links = [...article.querySelectorAll('a[href]')].filter(link => belongsTo(link, article));
        const link = links.find(a => /\\/groups\\/[^/]+\\/(posts|permalink)\\/\\d+/.test(a.href))
            || links.find(a => /\\/commerce\\/listing\\/\\d+/.test(a.href));
        const groupLink = links.find(a => /\\/groups\\/[^/]+(?:\\/|$)/.test(a.href));
        const timed = [...article.querySelectorAll('[data-utime], time[datetime]')].find(node => belongsTo(node, article));
        const clone = article.cloneNode(true);
        clone.querySelectorAll('[role="article"], [role="textbox"], [aria-label*="留言"], [aria-label*="comment"], [role="button"]').forEach(node => node.remove());
        const fallback = clone.innerText || clone.textContent || '';
        const content = body && body.innerText.trim() ? body.innerText : fallback;
        return {text: content, extraction: body && body.innerText.trim() ? 'message' : 'fallback', href: link ? link.href : '', groupId: groupLink ? new URL(groupLink.href).pathname.split('/')[2] : null, author: null,
            imageUrl: null, timestamp: timed ? (timed.getAttribute('data-utime') || timed.getAttribute('datetime')) : null,
            timeLabel: link ? (link.getAttribute('aria-label') || link.innerText) : null};
    });
    }""")  # type: ignore[attr-defined]


def _canonical_url(href: str) -> str:
    absolute = urljoin("https://www.facebook.com", href)
    parts = urlsplit(absolute)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def has_usable_posts(records: list[dict]) -> bool:
    return any(record.get('text', '').strip() and (_POST_URL.search(record.get('href', '')) or _COMMERCE_URL.search(record.get('href', ''))) for record in records)


def post_from_article(
    text: str,
    href: str,
    *,
    author: str | None = None,
    image_url: str | None = None,
    timestamp: str | None = None,
    time_label: str | None = None,
    now: datetime | None = None,
    group_id: str | None = None,
) -> RawGroupPost | None:
    match = _POST_URL.search(href)
    commerce = _COMMERCE_URL.search(href)
    content = text.strip()
    if not (match or commerce) or not content:
        return None
    if commerce and not match and not group_id:
        return None
    created_at: datetime | None = None
    if timestamp:
        try:
            created_at = (
                datetime.fromtimestamp(int(timestamp), timezone.utc)
                if timestamp.isdigit()
                else datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            )
        except (ValueError, OverflowError):
            pass
    if created_at is None and time_label:
        created_at = parse_posted_at(time_label, now)
        absolute = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?:.*?(\d{1,2}):(\d{2}))?', time_label)
        if created_at is None and absolute:
            from zoneinfo import ZoneInfo
            try:
                year, month, day, hour, minute = absolute.groups()
                created_at = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0), tzinfo=ZoneInfo('Asia/Taipei'))
            except ValueError:
                pass
    return RawGroupPost(
        source_id=match.group(2) if match else f'commerce:{commerce.group(1)}',
        group_id=match.group(1) if match else group_id,
        text=content,
        url=_canonical_url(href),
        author=author.strip() if author and author.strip() else None,
        image_url=image_url,
        created_at=created_at,
    )


class PlaywrightGroupCollector:
    def __init__(
        self,
        profile_dir: Path,
        group_urls: tuple[str, ...],
        *,
        headless: bool = False,
        max_scrolls: int = 3,
    ) -> None:
        self._profile_dir = profile_dir
        self._group_urls = group_urls
        self._headless = headless
        self._max_scrolls = max_scrolls

    @staticmethod
    def _playwright() -> object:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install -e '.[facebook]' && playwright install chromium"
            ) from error
        return sync_playwright()

    def posts(self) -> list[RawGroupPost]:
        if not self._group_urls:
            raise ValueError("FACEBOOK_GROUP_URLS is empty")
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        found: dict[str, RawGroupPost] = {}
        with self._playwright() as playwright:  # type: ignore[attr-defined]
            context = playwright.chromium.launch_persistent_context(
                self._profile_dir, headless=self._headless, locale="zh-TW"
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                for group_url in self._group_urls:
                    started = time.monotonic()
                    before = len(found)
                    diagnostics = {'articles': 0, 'with_link': 0, 'with_text': 0, 'fallback': 0}
                    mode = 'requested_chronological'
                    try:
                        page.goto(group_url.rstrip('/') + '/?sorting_setting=CHRONOLOGICAL', wait_until="domcontentloaded", timeout=60_000)
                        if "login" in page.url or page.locator('input[name="email"]').count():
                            raise RuntimeError("Facebook 尚未登入，請先執行：python main.py marketplace-login")
                        try:
                            page.locator('[data-ad-preview="message"], [data-ad-comet-preview="message"]').first.wait_for(state='visible', timeout=15_000)
                        except Exception:
                            LOGGER.warning('Group has no visible message markers after waiting: %s', group_url)
                        body_text = page.locator('body').inner_text(timeout=5000)
                        if any(message in body_text for message in ('此內容目前無法查看', '內容目前無法顯示', '加入社團以查看', 'This content isn’t available')):
                            LOGGER.warning('Group inaccessible or membership required: %s', group_url)
                            continue
                        if page.get_by_text('新貼文', exact=True).count() == 0:
                            LOGGER.warning('Group chronological sorting not confirmed: %s', group_url)
                        # A visible message does not imply its permalink has loaded.
                        for _ in range(5):
                            if has_usable_posts(snapshot(page)):
                                break
                            page.wait_for_timeout(2_000)
                        if not has_usable_posts(snapshot(page)):
                            LOGGER.warning('Chronological page has no paired post content/link; retrying plain group page: %s', group_url)
                            mode = 'plain_fallback_sort_unconfirmed'
                            page.goto(group_url, wait_until='domcontentloaded', timeout=60_000)
                            if 'login' in page.url or page.locator('input[name="email"]').count():
                                raise RuntimeError('Facebook 尚未登入，請先執行：python main.py marketplace-login')
                            for _ in range(8):
                                if has_usable_posts(snapshot(page)):
                                    break
                                page.wait_for_timeout(2_000)
                        for _ in range(self._max_scrolls + 1):
                            for label in ("查看更多", "顯示更多"):
                                controls = page.get_by_text(label, exact=True)
                                for index in range(min(controls.count(), 15)):
                                    try:
                                        controls.nth(index).click(timeout=300)
                                    except Exception:
                                        pass
                            for article in snapshot(page):
                                diagnostics['articles'] += 1
                                diagnostics['with_link'] += bool(article['href'])
                                diagnostics['with_text'] += bool(article['text'].strip())
                                diagnostics['fallback'] += article['extraction'] == 'fallback'
                                post = post_from_article(article['text'], article['href'], timestamp=article['timestamp'], time_label=article['timeLabel'], group_id=article.get('groupId') or urlsplit(group_url).path.strip('/').split('/')[1])
                                if post:
                                    found[f'{post.group_id}:{post.source_id}'] = post
                            page.mouse.wheel(0, 2_000)
                            page.wait_for_timeout(1_000)
                        for label in ("查看更多", "顯示更多"):
                            controls = page.get_by_text(label, exact=True)
                            for index in range(min(controls.count(), 30)):
                                try:
                                    controls.nth(index).click(timeout=500)
                                except Exception:
                                    pass
                        articles = snapshot(page)
                        for article in articles:
                            post = post_from_article(
                                article["text"], article["href"], author=article["author"],
                                image_url=article["imageUrl"], timestamp=article["timestamp"],
                                time_label=article["timeLabel"],
                                group_id=article.get('groupId') or urlsplit(group_url).path.strip('/').split('/')[1],
                            )
                            if post:
                                found[f"{post.group_id}:{post.source_id}"] = post
                    except RuntimeError:
                        raise
                    except Exception as error:
                        LOGGER.warning("Could not read Facebook group %s: %s", group_url, error)
                    finally:
                        LOGGER.info('Group extraction diagnostics %s: %s', group_url, diagnostics)
                        if len(found) == before:
                            LOGGER.warning('Group yielded no parsed posts; extraction/access remains unverified: %s', group_url)
                        LOGGER.info("Group %s posts=%d elapsed=%.1fs missing_time=%d sort=%s", group_url, len(found)-before, time.monotonic()-started, sum(p.created_at is None for p in found.values()), mode)
            finally:
                context.close()
        LOGGER.info("Facebook groups yielded %d unique posts", len(found))
        if not found:
            raise RuntimeError('Groups parsed zero posts across all groups; inspect Group extraction diagnostics and membership/access')
        return list(found.values())
