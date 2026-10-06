from app.collectors.groups.models import RawGroupPost
from app.collectors.marketplace.models import RawMarketplaceListing
from app.products.normalizer import normalize_group, normalize_marketplace


def test_normalize_marketplace() -> None:
    listing = normalize_marketplace(RawMarketplaceListing(
        "1", "iPhone 17 Pro Max 台北面交 售42,000", "https://test/1", location="桃園市"
    ))
    assert listing.source == "marketplace"
    assert listing.price == 42000
    assert listing.currency == "TWD"
    assert listing.location == "台北市"


def test_marketplace_falls_back_to_facebook_location() -> None:
    listing = normalize_marketplace(RawMarketplaceListing(
        "1", "iPhone 17 Pro Max 售42,000", "https://test/1", location="桃園市"
    ))
    assert listing.location == "桃園市"


def test_normalize_group() -> None:
    listing = normalize_group(RawGroupPost("2", "g1", "iPhone 17 Pro Max 256G 售42000 台中面交", "https://test/2"))
    assert listing.source == "group"
    assert listing.title == "iPhone 17 Pro Max"
    assert listing.price == 42000
    assert listing.location == "台中市"
