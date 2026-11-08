from dataclasses import replace
from types import SimpleNamespace
import pytest
from app.monitor_config import save_config
from app.products.custom_rules import assess_custom
from app.database.repository import ListingRepository
from app.notifications.telegram import format_listings
from app.fast_monitor import FastMonitor, Scheduler
from test_repository import make_listing


def configure(**product):
    return save_config({'groups': [{'url': 'https://www.facebook.com/groups/123/'}],
        'products': [{'keyword': 'iPhone 17 Pro Max', 'max_price': 35000, 'type': 'phone', 'source': 'group', **product}],
        'marketplace_enabled': False})


def test_pending_and_source_rules():
    configure(notify_uncertain=True)
    assert assess_custom('售 iPhone 17 Pro Max 256GB', None, source='group').status == 'pending'
    assert assess_custom('售 iPhone 17 Pro Max 256GB 售32000', 32000, source='marketplace').status == 'rejected'
    assert assess_custom('求購 iPhone 17 Pro Max 256GB 售32000', 32000, source='group').status == 'rejected'
    assert assess_custom('iPhone 17 Pro Max 256GB 已售出 售32000', 32000, source='group').status == 'rejected'
    assert assess_custom('售 iPhone 17 Pro Max 256GB 售38000', 38000, source='group').status == 'rejected'
    configure(notify_uncertain=False)
    assert assess_custom('售 iPhone 17 Pro Max 256GB', None, source='group').status == 'rejected'


def test_pending_persisted_and_notification_keeps_original(tmp_path):
    configure(notify_uncertain=True)
    listing = replace(make_listing(), source='group', title='售 iPhone 17 Pro Max 256GB', description='售 iPhone 17 Pro Max 256GB 盒裝完整', price=None, location='新竹市')
    with ListingRepository(tmp_path / 'db') as repo:
        assert repo.save(listing).is_eligible
        row = repo.get('group', listing.source_id)
        assert row['price'] is None and row['match_status'] == 'pending'
        message = format_listings(repo.list_recent(only_unnotified=True, only_eligible=True))
        assert '待確認' in message and '售 iPhone 17 Pro Max 256GB 盒裝完整' in message
        assert '商品：售 iPhone 17 Pro Max 256GB' not in message
        repo.mark_notified(row['id'])
        assert not repo.list_recent(only_unnotified=True, only_eligible=True)
        repo.save(replace(listing, description='售 iPhone 17 Pro Max 256GB 售32000', price=32000))
        assert repo.list_recent(only_unnotified=True, only_eligible=True)[0]['price'] == 32000


def test_disabled_marketplace_never_opens_page():
    configure()
    monitor = object.__new__(FastMonitor)
    monitor.search_page = SimpleNamespace(goto=lambda *args, **kwargs: pytest.fail('must not navigate'))
    monitor.marketplace()
    monitor.details()


def test_disabled_marketplace_does_not_block_groups():
    configure()
    monitor = object.__new__(FastMonitor)
    monitor.detail_queue = []
    now = [0]
    calls = []
    monitor.marketplace = lambda **kwargs: pytest.fail('disabled search executed')
    monitor.details = lambda: pytest.fail('disabled details executed')
    monitor.group = lambda url: (calls.append(url), now.__setitem__(0, now[0] + 1))
    monitor.notifications = lambda: now.__setitem__(0, now[0] + 1)
    monitor.run(Scheduler(('old',)), clock=lambda: now[0], sleep=lambda value: now.__setitem__(0, now[0] + value), duration=3)
    assert calls == ['https://www.facebook.com/groups/123/']


def test_disabled_marketplace_notifications_leave_groups_available(tmp_path, monkeypatch):
    from test_fast_monitor import bare_monitor
    configure(source='both', type='general')
    sent = []
    monkeypatch.setattr('app.fast_monitor.send_html', lambda *args, **kwargs: sent.append(args[2]))
    with ListingRepository(tmp_path / 'db') as repo:
        listing = replace(make_listing(), title='iPhone 17 Pro Max', description='售 iPhone 17 Pro Max 售32000', price=32000, location=None)
        repo.save(replace(listing, source='marketplace', source_id='market'))
        repo.save(replace(listing, source='group', source_id='group'))
        monitor = bare_monitor(repo)
        monitor.notifications(limit=1)
        assert len(sent) == 1
        assert repo.get('group', 'group')['notified_at'] is not None
        assert repo.get('marketplace', 'market')['notified_at'] is None


def test_phone_rule_uses_exact_model_capacity_price_and_region():
    save_config({'groups': [{'url': 'https://www.facebook.com/groups/123/'}], 'products': [{
        'keyword': 'iPhone 18 Pro', 'max_price': 45_000, 'type': 'phone',
        'capacity_gb': 256, 'regions': '新竹, 桃園', 'source': 'both',
    }]})
    assert assess_custom('售 iPhone 18 Pro 256GB 售價45000', 45_000, '新竹市').status == 'matched'
    assert assess_custom('售 iPhone 18 Pro 256GB 售價45000', 45_000, '桃園市').status == 'matched'
    assert assess_custom('售 iPhone 18 Pro Max 256GB 售價40400', 40_400, '新竹市').status == 'rejected'
    assert assess_custom('售 iPhone 18 Pro 512GB 售價45000', 45_000, '新竹市').status == 'rejected'
    assert assess_custom('售 iPhone 18 Pro 256GB 售價45001', 45_001, '新竹市').status == 'rejected'
    assert assess_custom('售 iPhone 18 Pro 256GB 售價45000', 45_000, '台中市').status == 'rejected'
    assert assess_custom('售 iPhone 18 Pro 256GB 附手機殼 售價45000', 45_000, '新竹市').status == 'matched'
    assert assess_custom('售 iPhone 18 Pro 256GB 手機殼 售價500', 500, '新竹市').status == 'rejected'


def test_new_price_limit_rechecked_before_sending_old_eligible_row(tmp_path, monkeypatch):
    from test_fast_monitor import bare_monitor
    configure(max_price=36000)
    sent = []
    monkeypatch.setattr('app.fast_monitor.send_html', lambda *args, **kwargs: sent.append(args))
    with ListingRepository(tmp_path / 'db') as repo:
        listing = replace(make_listing(), source='group', title='iPhone 17 Pro Max', description='售 iPhone 17 Pro Max 256GB 售35000', price=35000)
        assert repo.save(listing).is_eligible
        configure(max_price=32000)
        bare_monitor(repo).notifications()
        assert not sent
        assert not repo.get('group', listing.source_id)['eligible']
