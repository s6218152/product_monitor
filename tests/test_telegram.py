from datetime import datetime, timezone
from pathlib import Path
import json

from app.database.models import ProductListing
from app.database.repository import ListingRepository
import app.notifications.telegram as telegram
from app.notifications.telegram import _split_message, format_listings, send_html


def test_formats_listing_as_telegram_html(tmp_path: Path) -> None:
    listing = ProductListing(
        source="marketplace", source_id="1", title="iPhone <17> Pro Max 256GB",
        description=None, price=42000, currency="TWD", seller=None, location="台中市",
        url="https://example.test/item?a=1&b=2", image_url=None, condition=None,
        created_at=datetime(2026, 10, 6, 13, 58, tzinfo=timezone.utc),
        first_seen_at=datetime.now(timezone.utc),
    )
    with ListingRepository(tmp_path / "test.db") as repository:
        repository.save(listing)
        message = format_listings(repository.list_recent())

    assert "📱 容量：<b>256G</b>" in message
    assert "💰 TWD 42,000" in message
    assert "📍 地區：台中市" in message
    assert "🕒 上架：2026/10/06 21:58" in message
    assert (
        '🔗 商品連結：<a href="https://example.test/item?a=1&amp;b=2">'
        'https://example.test/item?a=1&amp;b=2</a>'
    ) in message


def test_splits_telegram_message_on_block_boundary() -> None:
    assert _split_message("header\n\none\n\ntwo", limit=11) == ["header\n\none", "two"]


def test_formats_terabytes_as_gigabytes(tmp_path: Path) -> None:
    listing = ProductListing(
        source="marketplace", source_id="2", title="iPhone 17 Pro Max 1TB",
        description=None, price=50000, currency="TWD", seller=None, location=None,
        url="https://example.test/2", image_url=None, condition=None,
        created_at=datetime(2026, 10, 6, tzinfo=timezone.utc),
        first_seen_at=datetime.now(timezone.utc),
    )
    with ListingRepository(tmp_path / "tb.db") as repository:
        repository.save(listing)
        message = format_listings(repository.list_recent())
    assert "📱 容量：<b>1024G</b>" in message


def test_sends_html_to_telegram(monkeypatch: object) -> None:
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok": true}'

    def fake_urlopen(request: object, timeout: int) -> Response:
        captured["data"] = json.loads(request.data)  # type: ignore[attr-defined]
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(telegram, "urlopen", fake_urlopen)  # type: ignore[attr-defined]
    assert send_html("secret", "123", "<b>Hello</b>") == 1
    assert captured["data"] == {
        "chat_id": "123",
        "text": "<b>Hello</b>",
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }
