from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

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

        # A migrated legacy NOT NULL timestamp must accept unknown post times.
        repository.save(replace(make_listing(), source_id="unknown-time", created_at=None))
        assert repository.get("marketplace", "unknown-time")["last_seen_at"] is None


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


def eligible_listing(**changes: object) -> ProductListing:
    values = {"title": "iPhone 17 Pro Max 256G", "location": "新竹縣"}
    values.update(changes)
    return replace(make_listing(32_000), **values)


def test_save_many_is_one_transaction_and_rolls_back(tmp_path: Path) -> None:
    with ListingRepository(tmp_path / "test.db") as repository:
        statements: list[str] = []
        repository._connection.set_trace_callback(statements.append)
        results = repository.save_many([eligible_listing(), eligible_listing(source_id="two")])
        assert [result.is_new for result in results] == [True, True]
        assert all(result.is_eligible for result in results)
        assert sum(statement == "COMMIT" for statement in statements) == 1
        with pytest.raises(sqlite3.IntegrityError):
            repository.save_many([
                eligible_listing(source_id="three"),
                eligible_listing(source_id="invalid", title=None),
            ])
        assert repository.count() == 2


def test_observation_preserves_post_time_and_refreshes_age(tmp_path: Path) -> None:
    with ListingRepository(tmp_path / "test.db") as repository:
        repository.save(eligible_listing())
        row = repository.get("marketplace", "same-id")
        assert row["storage_gb"] == 256
        assert row["eligible"] == 1
        assert row["last_seen_at"] == "2026-10-05T08:30:00+00:00"
        assert datetime.fromisoformat(row["observed_at"]) >= datetime.fromisoformat(row["first_seen_at"])


def test_prune_keeps_recent_observations_and_pending_price_drops(tmp_path: Path) -> None:
    from datetime import timedelta

    old = datetime.now(timezone.utc) - timedelta(days=100)
    with ListingRepository(tmp_path / "test.db") as repository:
        for source_id in ("fresh", "pending", "expired"):
            repository.save(eligible_listing(source_id=source_id, first_seen_at=old))
            repository.mark_notified(repository.get("marketplace", source_id)["id"])
        repository.save(eligible_listing(source_id="pending", first_seen_at=old, price=31_000))
        repository._connection.execute(
            "UPDATE listings SET observed_at=? WHERE source_id IN ('pending', 'expired')",
            (old.isoformat(),),
        )
        repository._connection.commit()
        assert repository.prune(90) == 1
        assert repository.get("marketplace", "fresh") is not None
        assert repository.get("marketplace", "pending") is not None
        assert repository.get("marketplace", "expired") is None


def test_mark_notified_records_sent_snapshot_price(tmp_path: Path) -> None:
    with ListingRepository(tmp_path / "test.db") as repository:
        repository.save(eligible_listing())
        row = repository.list_recent(only_unnotified=True)[0]
        repository.save(eligible_listing(price=30_000))
        repository.mark_notified(row["id"], sent_price=row["price"])
        assert repository.get("marketplace", "same-id")["notified_price"] == 32_000
        assert len(repository.list_recent(only_unnotified=True)) == 1


def test_failed_notification_backoff_and_success_reset(tmp_path: Path) -> None:
    with ListingRepository(tmp_path / "test.db") as repository:
        repository.save(eligible_listing())
        row = repository.list_recent(only_unnotified=True)[0]
        repository.mark_notification_failed(row["id"], "rejected", retry_after_seconds=300)
        assert repository.list_recent(only_unnotified=True) == []
        assert len(repository.list_recent()) == 1
        repository.mark_notification_failed(row["id"], "retry now", retry_after_seconds=0)
        assert len(repository.list_recent(only_unnotified=True)) == 1
        repository.mark_notified(row["id"], sent_price=row["price"])
        saved = repository.get("marketplace", "same-id")
        assert saved["notification_attempts"] == 0
        assert saved["notification_error"] is None
        assert saved["notification_next_attempt_at"] is None


def test_eligible_notification_query_uses_sorted_index(tmp_path: Path) -> None:
    with ListingRepository(tmp_path / "test.db") as repository:
        repository.save(eligible_listing())
        statements: list[str] = []
        repository._connection.set_trace_callback(statements.append)
        rows = repository.list_recent(1, ("新竹縣", "桃園市"), only_unnotified=True, only_eligible=True)
        assert len(rows) == 1
        sql = next(statement for statement in statements if statement.lstrip().startswith("SELECT id"))
        plan = [row["detail"] for row in repository._connection.execute(f"EXPLAIN QUERY PLAN {sql}")]
        assert any("USING INDEX" in detail for detail in plan)
        assert all("USE TEMP B-TREE" not in detail for detail in plan)


def test_migration_backfills_product_fields_without_resetting_notifications(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.executescript("""
        CREATE TABLE listings (
            id INTEGER PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL,
            title TEXT NOT NULL, description TEXT, price INTEGER,
            currency TEXT NOT NULL, seller TEXT, location TEXT, url TEXT NOT NULL,
            image_url TEXT, condition TEXT, created_at TEXT,
            first_seen_at TEXT NOT NULL, last_seen_at TEXT,
            notified_at TEXT, notified_price INTEGER,
            UNIQUE(source, source_id)
        );
        INSERT INTO listings VALUES (
            1, 'marketplace', 'old', 'iPhone 17 Pro Max 256G', NULL, 32000,
            'TWD', NULL, '新竹縣', 'https://test/item', NULL, NULL,
            NULL, '2026-01-01T00:00:00+00:00', NULL,
            '2026-01-02T00:00:00+00:00', 33000
        );
    """)
    connection.close()
    with ListingRepository(database) as repository:
        row = repository.get("marketplace", "old")
        assert (row["storage_gb"], row["eligible"]) == (256, 1)
        assert row["notified_price"] == 33_000
        assert row["observed_at"] == "2026-01-01T00:00:00+00:00"
        assert row["notification_attempts"] == 0
        assert len(repository.list_recent(only_unnotified=True, only_eligible=True)) == 1


def test_chat_cooldown_survives_restart_and_applies_to_new_observations(tmp_path):
    database = tmp_path / "test.db"
    with ListingRepository(database) as repository:
        repository.save(eligible_listing())
        repository.defer_notifications(3600)
    with ListingRepository(database) as repository:
        repository.save(eligible_listing(source_id="new-item"))
        assert repository.list_recent(only_unnotified=True, only_eligible=True) == []
        assert len(repository.list_recent(only_eligible=True)) == 2


def test_prune_removes_expired_rejected_observations(tmp_path):
    from datetime import timedelta

    old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    with ListingRepository(tmp_path / "test.db") as repository:
        repository.save(eligible_listing(price=99_000))
        repository._connection.execute("UPDATE listings SET observed_at=?", (old,))
        repository._connection.commit()
        assert repository.prune(90) == 1
        assert repository.count() == 0
