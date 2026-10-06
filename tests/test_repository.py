from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from app.database.models import ProductListing
from app.database.repository import ListingRepository


def make_listing(price: int = 42000) -> ProductListing:
    posted_at = datetime(2026, 10, 5, 8, 30, tzinfo=timezone.utc)
    return ProductListing(
        source="marketplace", source_id="same-id", title="iPhone 17 Pro Max", description=None,
        price=price, currency="TWD", seller=None, location="台中市",
        url="https://test/item", image_url=None, condition=None, created_at=posted_at,
        first_seen_at=datetime.now(timezone.utc),
    )


def test_save_deduplicates_and_updates(tmp_path: Path) -> None:
    with ListingRepository(tmp_path / "test.db") as repository:
        first = repository.save(make_listing())
        first_seen = repository.get("marketplace", "same-id")["first_seen_at"]
        second = repository.save(make_listing(price=41000))
        row = repository.get("marketplace", "same-id")
        assert first.is_new
        assert not second.is_new
        assert repository.count() == 1
        assert row["price"] == 41000
        assert row["first_seen_at"] == first_seen
        assert row["last_seen_at"] == "2026-10-05T08:30:00+00:00"
        assert row["location"] == "台中市"
        assert row["notified_at"] is None
        repository.mark_notified(row["id"])
        assert repository.get("marketplace", "same-id")["notified_at"] is not None
        assert repository.list_recent(only_unnotified=True) == []


def test_preserves_legacy_location_and_post_time(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.executescript("""
        CREATE TABLE listings (
            id INTEGER PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL,
            title TEXT NOT NULL, description TEXT, price INTEGER,
            currency TEXT NOT NULL, seller TEXT, location TEXT, url TEXT NOT NULL,
            image_url TEXT, condition TEXT, created_at TEXT,
            first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
            UNIQUE(source, source_id)
        );
        INSERT INTO listings VALUES (
            1, 'group', 'post-1', 'iPhone 17 Pro Max', NULL, 42000,
            'TWD', 'Alice', '台中', 'https://test/post-1', NULL, NULL,
            '2026-10-04T12:00:00+00:00', '2026-10-05T00:00:00+00:00',
            '2026-10-06T00:00:00+00:00'
        );
    """)
    connection.close()

    with ListingRepository(database) as repository:
        row = repository.get("group", "post-1")
        assert row["location"] == "台中"
        assert row["last_seen_at"] == "2026-10-06T00:00:00+00:00"
        assert row["notified_at"] is None


def test_adds_location_to_database_without_column(tmp_path: Path) -> None:
    database = tmp_path / "without-location.db"
    connection = sqlite3.connect(database)
    connection.executescript("""
        CREATE TABLE listings (
            id INTEGER PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL,
            title TEXT NOT NULL, description TEXT, price INTEGER,
            currency TEXT NOT NULL, seller TEXT, url TEXT NOT NULL,
            image_url TEXT, condition TEXT, created_at TEXT,
            first_seen_at TEXT NOT NULL, last_seen_at TEXT,
            UNIQUE(source, source_id)
        );
    """)
    connection.close()
    with ListingRepository(database) as repository:
        columns = {
            row[1] for row in repository._connection.execute("PRAGMA table_info(listings)").fetchall()  # noqa: SLF001
        }
        assert {"location", "notified_at"} <= columns
