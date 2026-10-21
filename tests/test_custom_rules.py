from dataclasses import replace
from types import SimpleNamespace
import pytest
from app.monitor_config import save_config, validate
from app.products.custom_rules import voucher_price, assess_custom
from app.database.repository import ListingRepository
from app.notifications.telegram import format_listings
from app.fast_monitor import FastMonitor, Scheduler
from test_repository import make_listing


def configure(**product):
    return save_config({'groups': [{'url': 'https://www.facebook.com/groups/123/'}],
        'products': [{'keyword': '禮券', 'max_price': 1000, 'type': 'voucher', 'source': 'group', **product}],
        'marketplace_enabled': False})


@pytest.mark.parametrize('text,expected',[
    ('出售全家禮券 面額1000 售950元',950),('禮券 面額1000 95折',950),
    ('禮券 面額1000 9.5折',950),('禮券 面額1000',None),
    ('禮券 面額1000 售95折',950),('禮券 面額1000 售 95 折',950),
    ('禮券 面額1000 售950；面額500 售480',None),('禮券 面額1000 3張 售950',None),
    ('禮券 面額1000 1張 售950',950),('禮券 面額1000 95折 9折',None)])
def test_voucher_price(text, expected):
    assert voucher_price(text)==expected


def test_pending_and_source_rules():
    configure(notify_uncertain=True)
    assert assess_custom('售禮券 面額1000',1000,source='group').status=='pending'
    assert assess_custom('售禮券 面額1000',1000,source='marketplace').status=='rejected'
    assert assess_custom('求購禮券 售950',950,source='group').status=='rejected'
    assert assess_custom('禮券已售出 售950',950,source='group').status=='rejected'
    assert assess_custom('售禮券 售1100',1100,source='group').status=='rejected'
    configure(notify_uncertain=False)
    assert assess_custom('售禮券 面額1000',1000,source='group').status=='rejected'


def test_pending_persisted_and_notification_keeps_original(tmp_path):
    configure(notify_uncertain=True)
    listing=replace(make_listing(),source='group',title='全家禮券',description='出售禮券 面額1000',price=1000,location=None)
    with ListingRepository(tmp_path/'db') as repo:
        assert repo.save(listing).is_eligible
        row=repo.get('group',listing.source_id)
        assert row['price'] is None and row['match_status']=='pending'
        message=format_listings(repo.list_recent(only_unnotified=True,only_eligible=True))
        assert '待確認' in message and '出售禮券 面額1000' in message
        repo.mark_notified(row['id'])
        assert not repo.list_recent(only_unnotified=True,only_eligible=True)
        repo.save(replace(listing,description='出售禮券 面額1000 售950'))
        assert repo.list_recent(only_unnotified=True,only_eligible=True)[0]['price']==950


def test_disabled_marketplace_never_opens_page():
    configure()
    monitor=object.__new__(FastMonitor)
    monitor.search_page=SimpleNamespace(goto=lambda *args,**kwargs:pytest.fail('must not navigate'))
    monitor.marketplace()
    monitor.details()


def test_disabled_marketplace_does_not_block_groups():
    configure()
    monitor=object.__new__(FastMonitor)
    monitor.detail_queue=[]
    now=[0];calls=[]
    monitor.marketplace=lambda **kwargs:pytest.fail('disabled search executed')
    monitor.details=lambda:pytest.fail('disabled details executed')
    monitor.group=lambda url:(calls.append(url),now.__setitem__(0,now[0]+1))
    monitor.notifications=lambda:now.__setitem__(0,now[0]+1)
    monitor.run(Scheduler(('old',)),clock=lambda:now[0],sleep=lambda value:now.__setitem__(0,now[0]+value),duration=3)
    assert calls==['https://www.facebook.com/groups/123/']


def test_disabled_marketplace_notifications_leave_groups_available(tmp_path, monkeypatch):
    from test_fast_monitor import bare_monitor
    configure(source='both',type='general')
    sent=[]
    monkeypatch.setattr('app.fast_monitor.send_html',lambda *args,**kwargs:sent.append(args[2]))
    with ListingRepository(tmp_path/'db') as repo:
        listing=replace(make_listing(),title='禮券',description='售禮券 售950',price=950,location=None)
        repo.save(replace(listing,source='marketplace',source_id='market'))
        repo.save(replace(listing,source='group',source_id='group'))
        monitor=bare_monitor(repo)
        monitor.notifications(limit=1)
        assert len(sent)==1
        assert repo.get('group','group')['notified_at'] is not None
        assert repo.get('marketplace','market')['notified_at'] is None
