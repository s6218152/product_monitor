from dataclasses import replace
from app.products.target_filter import rejection_reason
from app.products.location_parser import parse_location
from app.products.price_parser import parse_price
from app.database.repository import ListingRepository
from test_repository import make_listing


def test_gift_case_is_not_excluded():
    assert rejection_reason('iPhone 17 Pro Max 512G 附手機殼', 36000, '新竹縣') is None
    assert rejection_reason('iPhone 17 Pro Max 512G 售手機殼', 500, '新竹縣') is not None


def test_town_and_sale_price():
    assert parse_location('竹北面交') == '新竹縣'
    assert parse_location('中壢面交') == '桃園市'
    assert parse_location('頭份面交') == '苗栗縣'
    assert parse_price('原價 45000 售價 31000') == 31000


def test_unknown_time_and_price_drop_notification(tmp_path):
    with ListingRepository(tmp_path / 'db') as repo:
        item = replace(make_listing(32000), created_at=None)
        repo.save(item)
        row = repo.list_recent(only_unnotified=True)[0]
        repo.mark_notified(row['id'])
        repo.save(replace(item, price=33000))
        assert repo.list_recent(only_unnotified=True) == []
        repo.save(replace(item, price=31000))
        assert len(repo.list_recent(only_unnotified=True)) == 1
