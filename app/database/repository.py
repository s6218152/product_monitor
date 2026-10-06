from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from .models import ProductListing
from .sqlite import connect, initialize


@dataclass(frozen=True, slots=True)
class SaveResult:
    is_new: bool


class ListingRepository:
    def __init__(self, database_path: Path) -> None:
        self._connection = connect(database_path)
        initialize(self._connection)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "ListingRepository":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def save(self, listing: ProductListing) -> SaveResult:
        exists = self.get(listing.source, listing.source_id) is not None
        values = (
            listing.source, listing.source_id, listing.title, listing.description,
            listing.price, listing.currency, listing.seller, listing.location, listing.url,
            listing.image_url, listing.condition,
            listing.created_at.isoformat() if listing.created_at else None,
            listing.first_seen_at.isoformat(),
            listing.created_at.isoformat() if listing.created_at else None,
        )
        self._connection.execute(
            """INSERT INTO listings (
                source, source_id, title, description, price, currency, seller, location,
                url, image_url, condition, created_at, first_seen_at,
                last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, source_id) DO UPDATE SET
                title=excluded.title, description=excluded.description,
                price=excluded.price, currency=excluded.currency,
                seller=excluded.seller, location=excluded.location,
                url=excluded.url, image_url=excluded.image_url,
                condition=excluded.condition,
                created_at=COALESCE(excluded.created_at, listings.created_at),
                last_seen_at=COALESCE(excluded.last_seen_at, listings.last_seen_at)
            """,
            values,
        )
        self._connection.commit()
        return SaveResult(is_new=not exists)

    def count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) AS count FROM listings").fetchone()
        return int(row["count"])

    def get(self, source: str, source_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM listings WHERE source = ? AND source_id = ?",
            (source, source_id),
        ).fetchone()

    def list_recent(
        self,
        limit: int | None = 10,
        locations: tuple[str, ...] = (),
        *,
        only_unnotified: bool = False,
    ) -> list[sqlite3.Row]:
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")
        location_filter = ""
        parameters: list[object] = []
        if locations:
            placeholders = ", ".join("?" for _ in locations)
            location_filter = f" AND location IN ({placeholders})"
            parameters.extend(locations)
        notification_filter = " AND notified_at IS NULL" if only_unnotified else ""
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ?"
            parameters.append(limit)
        return list(self._connection.execute(
            f"""SELECT id, title, description, price, currency, location, url,
                last_seen_at, notified_at
            FROM listings
            WHERE last_seen_at IS NOT NULL
            {location_filter}
            {notification_filter}
            ORDER BY last_seen_at DESC
            {limit_clause}""",
            parameters,
        ).fetchall())

    def mark_notified(self, listing_id: int) -> None:
        self._connection.execute(
            "UPDATE listings SET notified_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), listing_id),
        )
        self._connection.commit()
