from datetime import datetime, timezone

from app.collectors.marketplace.playwright_client import (
    listing_from_link,
    parse_creation_time,
    parse_facebook_description,
    parse_facebook_location,
    parse_posted_at,
)


def test_listing_from_marketplace_link() -> None:
    listing = listing_from_link(
        "/marketplace/item/123456789/?ref=search",
        "NT$42,000\niPhone 17 Pro Max 256GB 黑色\n台中市",
    )
    assert listing is not None
    assert listing.source_id == "123456789"
    assert listing.title == "iPhone 17 Pro Max 256GB 黑色"
    assert listing.price == 42000
    assert listing.url == "https://www.facebook.com/marketplace/item/123456789"


def test_non_listing_link_is_ignored() -> None:
    assert listing_from_link("/marketplace/category/phones", "Phones") is None


def test_parse_relative_facebook_post_time() -> None:
    now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    assert parse_posted_at("2天前", now) == datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
    assert parse_posted_at("3小時前於台中市, 台灣上架", now) == datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)


def test_unknown_facebook_post_time_is_none() -> None:
    assert parse_posted_at("台中市, 台灣", datetime.now(timezone.utc)) is None


def test_parse_creation_time_for_current_listing_only() -> None:
    html = (
        '"id":"123","creation_time":1790660825,'
        '"id":"recommended","creation_time":1790999999'
    )
    assert parse_creation_time(html, "123") == datetime.fromtimestamp(1790660825, timezone.utc)
    assert parse_creation_time(html, "missing") is None


def test_parse_facebook_location_for_current_listing() -> None:
    html = (
        '"id":"123","creation_time":1790660825,'
        '"location_text":{"text":"\\u6843\\u5712\\u5e02, \\u53f0\\u7063"}'
    )
    assert parse_facebook_location(html, "123") == "桃園市"


def test_parse_facebook_description_for_current_listing() -> None:
    html = (
        '"id":"123","creation_time":1790660825,'
        '"redacted_description":{"text":"【容量】：512G\\n盒裝完整"},'
        '"id":"recommended","redacted_description":{"text":"256G"}'
    )
    assert parse_facebook_description(html, "123") == "【容量】：512G\n盒裝完整"
    assert parse_facebook_description(html, "missing") is None
