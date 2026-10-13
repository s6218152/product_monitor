from datetime import datetime, timezone
import json
from unittest.mock import Mock

import pytest

from app.collectors.marketplace.playwright_client import (
    listing_from_link,
    parse_creation_time,
    parse_facebook_description,
    parse_facebook_location,
    parse_posted_at,
    PlaywrightMarketplaceCollector,
)


def embedded_listings(*items: dict) -> str:
    payload = json.dumps({"data": list(items)}, separators=(",", ":"))
    return f'<script type="application/json">{payload}</script>'


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
        embedded_listings(
            {"id": "123", "creation_time": 1790660825},
            {"id": "recommended", "creation_time": 1790999999},
        )
    )
    assert parse_creation_time(html, "123") == datetime.fromtimestamp(1790660825, timezone.utc)
    assert parse_creation_time(html, "missing") is None


def test_parse_facebook_location_for_current_listing() -> None:
    html = embedded_listings({"id": "123", "location_text": {"text": "桃園市, 台灣"}})
    assert parse_facebook_location(html, "123") == "桃園市"


def test_parse_facebook_description_for_current_listing() -> None:
    html = embedded_listings(
        {"id": "123", "redacted_description": {"text": "【容量】：512G\n盒裝完整"}},
        {"id": "recommended", "redacted_description": {"text": "256G"}},
    )
    assert parse_facebook_description(html, "123") == "【容量】：512G\n盒裝完整"
    assert parse_facebook_description(html, "missing") is None


@pytest.mark.parametrize("parser", [parse_creation_time, parse_facebook_location, parse_facebook_description])
def test_missing_fields_never_come_from_another_listing(parser) -> None:
    html = embedded_listings(
        {"id": "123", "title": "current"},
        {
            "id": "999", "creation_time": 1790660825,
            "location_text": {"text": "台北市, 台灣"},
            "redacted_description": {"text": "recommended 256G"},
        },
    )
    assert parser(html, "123") is None


def test_listing_fields_before_id_and_repeated_reference() -> None:
    html = embedded_listings(
        {"id": "123"},
        {
            "creation_time": 1790660825,
            "location_text": {"text": "桃園市, 台灣"},
            "redacted_description": {"text": "512G"}, "id": "123",
        },
    )
    assert parse_creation_time(html, "123") == datetime.fromtimestamp(1790660825, timezone.utc)
    assert parse_facebook_location(html, "123") == "桃園市"
    assert parse_facebook_description(html, "123") == "512G"


def test_details_keep_location_and_description_without_time() -> None:
    page = Mock()
    page.content.return_value = embedded_listings({
        "id": "123", "location_text": {"text": "桃園市, 台灣"},
        "redacted_description": {"text": "512G good condition"},
    })
    page.locator.return_value.count.return_value = 0
    assert PlaywrightMarketplaceCollector._read_details(page, "https://example.invalid/123", "123") == (
        None, "桃園市", "512G good condition",
    )


def test_search_accumulates_cards_before_virtualized_scroll(tmp_path, monkeypatch) -> None:
    page = Mock()
    page.url = "https://www.facebook.com/marketplace/search/"
    cards = [
        {"href": f"/marketplace/item/{item_id}/", "text": "NT$30,000\niPhone 17 Pro Max", "ariaLabel": None}
        for item_id in ("123", "456", "789")
    ]
    position = 0

    def scroll(*args):
        nonlocal position
        position += 1

    links = Mock()
    links.evaluate_all.side_effect = lambda script: [cards[position]]
    login = Mock()
    login.count.return_value = 0
    page.locator.side_effect = lambda selector: links if selector.startswith('a[') else login
    page.mouse.wheel.side_effect = scroll
    context = Mock()
    context.pages = [page]
    playwright = Mock()
    playwright.chromium.launch_persistent_context.return_value = context
    manager = Mock()
    manager.__enter__ = Mock(return_value=playwright)
    manager.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(PlaywrightMarketplaceCollector, "_playwright", staticmethod(lambda: manager))
    monkeypatch.setattr(PlaywrightMarketplaceCollector, "_read_details", staticmethod(lambda *args: (None, None, None)))

    found = PlaywrightMarketplaceCollector(tmp_path, max_scrolls=2).search("iPhone 17 Pro Max")
    assert {item.source_id for item in found} == {"123", "456", "789"}
    context.close.assert_called_once()
