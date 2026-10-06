from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ProductListing:
    source: str
    source_id: str
    title: str
    description: str | None
    price: int | None
    currency: str
    seller: str | None
    location: str | None
    url: str
    image_url: str | None
    condition: str | None
    created_at: datetime | None
    first_seen_at: datetime
