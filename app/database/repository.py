from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from app.products.storage_parser import parse_storage_gb
from app.products.target_filter import rejection_reason
from .models import ProductListing
from .sqlite import connect, initialize


@dataclass(frozen=True, slots=True)
class SaveResult:
    is_new: bool
    is_eligible: bool
    rejection_reason: str | None = None


class ListingRepository:
    def __init__(self, database_path: Path) -> None:
        self._connection = connect(database_path)
        try:
            initialize(self._connection)
        except BaseException:
            self._connection.close()
            raise

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "ListingRepository":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def save(self, listing: ProductListing) -> SaveResult:
        return self.save_many([listing])[0]

    def save_many(self, listings: Iterable[ProductListing]) -> list[SaveResult]:
        listings = list(listings)
        if not listings:
            return []
        results: list[SaveResult] = []
        observed_at = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            existing: set[tuple[str, str]] = set()
            # Bound parameters for older SQLite builds; avoid a SELECT per item.
            for start in range(0, len(listings), 400):
                chunk = listings[start:start + 400]
                sources = tuple(dict.fromkeys(item.source for item in chunk))
                ids = tuple(dict.fromkeys(item.source_id for item in chunk))
                source_marks = ",".join("?" for _ in sources)
                id_marks = ",".join("?" for _ in ids)
                existing.update((row["source"], row["source_id"]) for row in self._connection.execute(
                    f"SELECT source, source_id FROM listings WHERE source IN ({source_marks}) AND source_id IN ({id_marks})",
                    (*sources, *ids),
                ))
            for listing in listings:
                text = f"{listing.title} {listing.description or ''}"
                reason = rejection_reason(text, listing.price, listing.location)
                pair = (listing.source, listing.source_id)
                posted_at = listing.created_at.isoformat() if listing.created_at else None
                self._connection.execute(
                    """INSERT INTO listings (
                        source, source_id, title, description, price, currency, seller, location,
                        url, image_url, condition, created_at, first_seen_at, last_seen_at,
                        storage_gb, eligible, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source, source_id) DO UPDATE SET
                        title=excluded.title, description=excluded.description,
                        price=excluded.price, currency=excluded.currency,
                        seller=excluded.seller, location=excluded.location,
                        url=excluded.url, image_url=excluded.image_url, condition=excluded.condition,
                        created_at=COALESCE(excluded.created_at, listings.created_at),
                        last_seen_at=COALESCE(excluded.last_seen_at, listings.last_seen_at),
                        storage_gb=excluded.storage_gb, eligible=excluded.eligible,
                        observed_at=excluded.observed_at""",
                    (listing.source, listing.source_id, listing.title, listing.description,
                     listing.price, listing.currency, listing.seller, listing.location,
                     listing.url, listing.image_url, listing.condition, posted_at,
                     listing.first_seen_at.isoformat(), posted_at, parse_storage_gb(text),
                     int(reason is None), observed_at),
                )
                results.append(SaveResult(pair not in existing, reason is None, reason))
                existing.add(pair)
        return results

    def count(self) -> int:
        return int(self._connection.execute("SELECT COUNT(*) AS count FROM listings").fetchone()["count"])

    def get(self, source: str, source_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM listings WHERE source = ? AND source_id = ?", (source, source_id),
        ).fetchone()

    def get_detail_task(self, source_id: str):
        return self._connection.execute('SELECT * FROM detail_tasks WHERE source_id=?', (source_id,)).fetchone()

    def defer_detail(self, *, source_id, payload, fingerprint, state, reason, attempts, delay_seconds, discovered_at):
        next_at = (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat()
        with self._connection:
            self._connection.execute('''INSERT INTO detail_tasks VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(source_id) DO UPDATE SET payload=excluded.payload, fingerprint=excluded.fingerprint,
                state=excluded.state, reason=excluded.reason, attempts=excluded.attempts,
                next_attempt_at=excluded.next_attempt_at''',
                (source_id, payload, fingerprint, state, reason, attempts, next_at, discovered_at))

    def due_detail_tasks(self, limit=5):
        return list(self._connection.execute('SELECT * FROM detail_tasks WHERE next_attempt_at<=? ORDER BY next_attempt_at LIMIT ?',
            (datetime.now(timezone.utc).isoformat(), limit)))

    def clear_detail_task(self, source_id):
        with self._connection:
            self._connection.execute('DELETE FROM detail_tasks WHERE source_id=?', (source_id,))

    def list_recent(
        self, limit: int | None = 10, locations: tuple[str, ...] = (), *,
        only_unnotified: bool = False, only_eligible: bool = False,
    ) -> list[sqlite3.Row]:
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")
        filters: list[str] = []
        parameters: list[object] = []
        if only_eligible:
            filters.append("eligible = 1")
        if locations:
            filters.append(f"location IN ({','.join('?' for _ in locations)})")
            parameters.extend(locations)
        if only_unnotified:
            now = datetime.now(timezone.utc).isoformat()
            filters.extend((
                "(notified_at IS NULL OR price < notified_price)",
                "(notification_next_attempt_at IS NULL OR notification_next_attempt_at <= ?)",
                "NOT EXISTS (SELECT 1 FROM notification_state WHERE id=1 AND next_attempt_at > ?)",
            ))
            parameters.extend((now, now))
        where = " AND ".join(filters) or "1=1"
        limit_clause = "LIMIT ?" if limit is not None else ""
        if limit is not None:
            parameters.append(limit)
        return list(self._connection.execute(
            f"""SELECT id, title, description, price, currency, location, url,
                       last_seen_at, notified_at, notified_price, storage_gb, eligible, observed_at, first_seen_at
                FROM listings WHERE {where}
                ORDER BY last_seen_at DESC, id DESC {limit_clause}""", parameters,
        ))

    def mark_notified(self, listing_id: int, sent_price: int | None = None) -> None:
        with self._connection:
            self._connection.execute(
                """UPDATE listings SET notified_at=?, notified_price=COALESCE(?, price),
                       notification_attempts=0, notification_error=NULL,
                       notification_next_attempt_at=NULL WHERE id=?""",
                (datetime.now(timezone.utc).isoformat(), sent_price, listing_id),
            )

    def mark_notification_failed(
        self, listing_id: int, error: str, *, retry_after_seconds: float = 300,
    ) -> None:
        if retry_after_seconds < 0:
            raise ValueError("retry delay must be nonnegative")
        next_attempt = datetime.now(timezone.utc) + timedelta(seconds=retry_after_seconds)
        with self._connection:
            self._connection.execute(
                """UPDATE listings SET notification_attempts=notification_attempts+1,
                       notification_error=?, notification_next_attempt_at=? WHERE id=?""",
                (error[:1000], next_attempt.isoformat(), listing_id),
            )

    def defer_notifications(self, retry_after_seconds: float) -> None:
        if retry_after_seconds < 0:
            raise ValueError("retry delay must be nonnegative")
        next_attempt = (datetime.now(timezone.utc) + timedelta(seconds=retry_after_seconds)).isoformat()
        with self._connection:
            self._connection.execute(
                """UPDATE notification_state SET next_attempt_at=?
                   WHERE id=1 AND (next_attempt_at IS NULL OR next_attempt_at < ?)""",
                (next_attempt, next_attempt),
            )

    def prune(self, days: int = 90) -> int:
        if days < 1:
            raise ValueError("retention days must be at least 1")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._connection:
            cursor = self._connection.execute(
                """DELETE FROM listings WHERE COALESCE(observed_at, first_seen_at) < ?
                   AND (eligible=0 OR (notified_at IS NOT NULL
                       AND (price IS NULL OR notified_price IS NULL OR price >= notified_price)))""",
                (cutoff,),
            )
        self._connection.execute("VACUUM")
        return cursor.rowcount
