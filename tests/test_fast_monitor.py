from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

from app.fast_monitor import FastMonitor, Scheduler
from app.database.repository import ListingRepository
from app.collectors.marketplace.models import RawMarketplaceListing
from test_repository import make_listing


def bare_monitor(repo):
    monitor = object.__new__(FastMonitor)
    monitor.repository = repo
    monitor.detail_queue = deque()
    monitor.queued = set()
    monitor.detail_retry = {}
    monitor.detail_attempts = {}
    monitor.discovery_times = {}
    monitor.settings = SimpleNamespace(telegram_bot_token='test', telegram_chat_id='test')
    return monitor


def test_fair_scheduler_and_start_based_interval():
    scheduler = Scheduler(('a', 'b'), marketplace_interval=120)
    job = scheduler.next(0)
    assert job.name == 'marketplace'
    scheduler.finish(job, 0, 30)
    assert job.due == 120
    assert scheduler.next(30).name == 'a'
    for name in ('a', 'b', 'details', 'notifications', 'catchup'):
        job = scheduler.next(30)
        assert job.name == name
        scheduler.finish(job, 30, 31)
    assert scheduler.next(120).name == 'details'


def test_incremental_save_sends_before_rest_of_scan(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr('app.fast_monitor.send_html', lambda *a, **k: sent.append(a[2]) or 1)
    with ListingRepository(tmp_path/'db') as repo:
        monitor = bare_monitor(repo)
        listing = replace(make_listing(32000), title='iPhone 17 Pro Max 256G', location='新竹縣')
        monitor.save(listing)
        assert len(sent) == 1
        assert repo.get(listing.source, listing.source_id)['notified_at']
        monitor.save(listing)
        assert len(sent) == 1


def test_known_cards_skipped_and_new_cards_prioritized(tmp_path):
    with ListingRepository(tmp_path/'db') as repo:
        monitor = bare_monitor(repo)
        repo.save(make_listing())
        known = RawMarketplaceListing(source_id='same-id', title='iPhone 17 Pro Max', url='https://test')
        monitor.enqueue(known)
        assert not monitor.detail_queue
        new = replace(known, source_id='new')
        monitor.enqueue(new)
        monitor.enqueue(new)
        assert len(monitor.detail_queue) == 1


def test_failed_send_is_retained_for_retry(tmp_path, monkeypatch):
    def fail(*a, **k):
        raise RuntimeError('network')
    monkeypatch.setattr('app.fast_monitor.send_html', fail)
    with ListingRepository(tmp_path/'db') as repo:
        monitor = bare_monitor(repo)
        listing = replace(make_listing(32000), title='iPhone 17 Pro Max 256G', location='新竹縣')
        import pytest
        with pytest.raises(RuntimeError):
            monitor.save(listing)
        row = repo.get(listing.source, listing.source_id)
        assert row['notified_at'] is None
        assert row['notification_attempts'] == 1


def test_fast_scan_requests_newest_and_queues_without_detail_navigation(tmp_path, monkeypatch):
    class Page:
        url = 'https://www.facebook.com/marketplace/search/'
        mouse = SimpleNamespace(wheel=lambda *a: None)
        def __init__(self):
            self.urls = []
        def goto(self, url, **kwargs):
            self.urls.append(url)
        def locator(self, selector):
            return SimpleNamespace(count=lambda: 0, all_text_contents=lambda: [])
        def wait_for_timeout(self, amount):
            pass
    with ListingRepository(tmp_path/'db') as repo:
        monitor = bare_monitor(repo)
        monitor.search_page = Page()
        monitor.catchup_scrolls = 6
        item = RawMarketplaceListing(source_id='new', title='iPhone 17 Pro Max 256G', url='https://test')
        def collect(page, found):
            found[item.source_id] = item
        monkeypatch.setattr('app.fast_monitor.PlaywrightMarketplaceCollector._collect_cards', collect)
        monitor.marketplace()
        assert 'sortBy=creation_time_descend' in monitor.search_page.urls[0]
        assert len(monitor.search_page.urls) == 1
        assert len(monitor.detail_queue) == 1
        assert repo.count() == 0  # Not validated yet: never notify from the card alone.


def test_failed_job_does_not_stop_other_sources(tmp_path):
    monitor = bare_monitor(None)
    monitor.detail_queue = deque()
    now = [0]
    calls = []
    monitor.alert = lambda *a: None
    def marketplace(**kwargs):
        calls.append('marketplace')
        now[0] += 1
        raise RuntimeError('login expired')
    def group(url):
        calls.append(url)
        now[0] += 1
    monitor.marketplace = marketplace
    monitor.group = group
    monitor.details = lambda: now.__setitem__(0, now[0]+1)
    monitor.notifications = lambda: now.__setitem__(0, now[0]+1)
    monitor.run(Scheduler(('group-a',)), clock=lambda: now[0], sleep=lambda x: now.__setitem__(0, now[0]+x), duration=3)
    assert calls[:2] == ['marketplace', 'group-a']


def test_detail_retry_is_retained_and_does_not_block_new_items(tmp_path, monkeypatch):
    with ListingRepository(tmp_path/'db') as repo:
        monitor = bare_monitor(repo)
        failed = RawMarketplaceListing(source_id='failed', title='iPhone 17 Pro Max', url='https://test')
        monitor.retry_detail(failed, 'TimeoutError')
        assert not monitor.detail_queue
        assert 'failed' not in monitor.queued
        assert repo.get_detail_task('failed')['state'] == 'transient_retry'
        monitor.details()  # No ready item: no page needed, retains deferred work.
        assert not monitor.detail_queue
        monitor.enqueue(replace(failed, source_id='new'))
        assert monitor.detail_queue[0].source_id == 'new'


def test_closed_search_page_recovers_without_stopping_groups(tmp_path):
    class TargetClosedError(Exception): pass
    monitor = bare_monitor(None)
    now = [0]
    recovered = []
    groups = []
    monitor.alert = lambda *a: None
    monitor.recover_page = lambda name: recovered.append(name)
    def fail(**kw):
        now[0] += 1
        raise TargetClosedError('closed')
    monitor.marketplace = fail
    def group(url):
        groups.append(url)
        now[0] += 1
    monitor.group = group
    monitor.details = lambda: now.__setitem__(0, now[0]+1)
    monitor.notifications = lambda: now.__setitem__(0, now[0]+1)
    monitor.run(Scheduler(('group-a',)), clock=lambda: now[0], duration=3)
    assert recovered == ['search_page']
    assert groups == ['group-a']


def test_context_loss_escalates_for_browser_rebuild():
    from app.fast_monitor import BrowserRecoveryNeeded
    import pytest
    monitor = object.__new__(FastMonitor)
    def fail(): raise RuntimeError('context closed')
    monitor.context = SimpleNamespace(new_page=fail)
    monitor.page_faults = set()
    with pytest.raises(BrowserRecoveryNeeded):
        monitor.new_page('search_page')


def test_page_crash_replaced_even_when_page_not_closed():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        monitor = object.__new__(FastMonitor)
        monitor.detail_queue = deque()
        monitor.attach_context(context)
        old = monitor.search_page
        monitor.page_faults.add('search_page')
        monitor.recover_page('search_page')
        assert old.is_closed()
        assert not monitor.search_page.is_closed()
        assert not monitor.group_page.is_closed()
        browser.close()


def test_empty_description_uses_title_and_source_location(tmp_path, monkeypatch):
    from app.collectors.marketplace import playwright_client as parser
    monkeypatch.setattr(parser, '_listing_data', lambda *a: {'creation_time': 1791873600, 'location_text': {'text': '新竹縣'}, 'redacted_description': {'text': ''}})
    monkeypatch.setattr('app.fast_monitor.send_html', lambda *a, **k: 1)
    with ListingRepository(tmp_path/'db') as repo:
        monitor = bare_monitor(repo)
        item = RawMarketplaceListing(source_id='title-only', title='iPhone 17 Pro Max 256G', price=32000, url='https://test')
        monitor.enqueue(item)
        monitor.detail_page = SimpleNamespace(url='https://test', goto=lambda *a, **k: None,
            wait_for_timeout=lambda *a: None, content=lambda: '', locator=lambda *a: SimpleNamespace(count=lambda:0))
        monitor.details()
        row = repo.get('marketplace', item.source_id)
        assert row['eligible'] == 1
        assert row['notified_at'] is not None
        assert not monitor.detail_queue


def test_missing_capacity_is_explicit_and_not_notified(tmp_path, monkeypatch):
    from app.collectors.marketplace import playwright_client as parser
    monkeypatch.setattr(parser, '_listing_data', lambda *a: {'location_text': {'text': '新竹縣'}})
    with ListingRepository(tmp_path/'db') as repo:
        monitor = bare_monitor(repo)
        item = RawMarketplaceListing(source_id='missing', title='iPhone 17 Pro Max', price=32000, url='https://test')
        monitor.enqueue(item)
        monitor.detail_page = SimpleNamespace(url='https://test', goto=lambda *a, **k: None,
            wait_for_timeout=lambda *a: None, content=lambda: '', locator=lambda *a: SimpleNamespace(count=lambda:0))
        monitor.details()
        assert repo.get('marketplace', item.source_id) is None
        assert not monitor.detail_queue
        assert repo.get_detail_task(item.source_id)['reason'] == 'missing_capacity'


def test_missing_fields_cooldown_survives_restart_and_changed_card_rechecks(tmp_path):
    from datetime import timedelta
    path = tmp_path/'db'
    item = RawMarketplaceListing(source_id='missing', title='iPhone 17 Pro Max', price=32000, url='https://test')
    with ListingRepository(path) as repo:
        monitor = bare_monitor(repo)
        monitor.retry_detail(item, 'missing_capacity')
        monitor.retry_detail(item, 'missing_capacity')
        task = repo.get_detail_task(item.source_id)
        assert task['state'] == 'awaiting_data'
        assert datetime.fromisoformat(task['next_attempt_at']) > datetime.now(timezone.utc)+timedelta(hours=5)
        assert not monitor.detail_queue
    with ListingRepository(path) as repo:
        monitor = bare_monitor(repo)
        monitor.enqueue(item)
        assert not monitor.detail_queue
        monitor.enqueue(replace(item, title='iPhone 17 Pro Max 256G'))
        assert len(monitor.detail_queue) == 1
        assert repo.get_detail_task(item.source_id) is None


def test_transient_errors_limit_fast_retries_even_when_error_type_changes(tmp_path):
    from datetime import timedelta
    with ListingRepository(tmp_path/'db') as repo:
        monitor = bare_monitor(repo)
        item = RawMarketplaceListing(source_id='network', title='iPhone 17 Pro Max', url='https://test')
        for reason in ('TimeoutError','TargetClosedError','missing_item_data'):
            monitor.retry_detail(item, reason)
        task = repo.get_detail_task(item.source_id)
        assert task['attempts'] == 3
        assert task['state'] == 'cooldown'
        assert datetime.fromisoformat(task['next_attempt_at']) > datetime.now(timezone.utc)+timedelta(minutes=14)


def test_due_database_retry_is_processed_without_search_rediscovery(tmp_path, monkeypatch):
    from app.collectors.marketplace import playwright_client as parser
    monkeypatch.setattr(parser, '_listing_data', lambda *a: {'location_text': {'text':'新竹縣'}})
    monkeypatch.setattr('app.fast_monitor.send_html', lambda *a, **k:1)
    with ListingRepository(tmp_path/'db') as repo:
        monitor = bare_monitor(repo)
        item = RawMarketplaceListing(source_id='recover',title='iPhone 17 Pro Max 256G',price=32000,url='https://test')
        monitor.retry_detail(item,'TimeoutError')
        with repo._connection:
            repo._connection.execute("UPDATE detail_tasks SET next_attempt_at='2000-01-01T00:00:00+00:00'")
        monitor.detail_page = SimpleNamespace(url='https://test',goto=lambda *a,**k:None,
            wait_for_timeout=lambda *a:None,content=lambda:'',locator=lambda *a:SimpleNamespace(count=lambda:0))
        monitor.details()
        assert repo.get_detail_task(item.source_id) is None
        assert repo.get('marketplace',item.source_id)['notified_at']


def test_sync_groups_preserves_jobs_and_replaces_removed_groups():
    scheduler = Scheduler(('old', 'retained'), group_interval=75)
    retained = next(job for job in scheduler.jobs if job.name == 'retained')
    retained.due = 123
    retained.last_finished = 100
    assert scheduler.sync_groups(('retained', 'new'))
    assert [job.name for job in scheduler.jobs] == ['marketplace', 'retained', 'new', 'details', 'notifications', 'catchup']
    assert scheduler.jobs[1] is retained
    assert retained.due == 123
    assert scheduler.jobs[2].due == 0
    assert scheduler.jobs[2].interval == 75
    assert not scheduler.sync_groups(('retained', 'new'))


def test_running_monitor_reloads_groups_without_restart(tmp_path, monkeypatch):
    from app.monitor_config import save_config
    monkeypatch.setenv('MONITOR_CONFIG_PATH', str(tmp_path/'settings.json'))
    monitor = bare_monitor(None)
    now = [0]
    calls = []
    monitor.marketplace = lambda **kw: now.__setitem__(0, now[0]+1)
    def group(url):
        calls.append(url)
        now[0] += 1
    monitor.group = group
    monitor.details = lambda: now.__setitem__(0, now[0]+1)
    monitor.notifications = lambda: now.__setitem__(0, now[0]+1)
    save_config({'groups': [{'url': 'https://www.facebook.com/groups/new/'}],
                 'products': [{'keyword': 'test', 'max_price': 100}]})
    scheduler = Scheduler(('old',))
    monitor.run(scheduler, clock=lambda: now[0], sleep=lambda value: now.__setitem__(0, now[0]+value), duration=4)
    assert calls == ['https://www.facebook.com/groups/new/']
    assert all(job.name != 'old' for job in scheduler.jobs)
