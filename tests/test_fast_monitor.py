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
