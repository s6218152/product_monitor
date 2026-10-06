from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RawMarketplaceListing:
    source_id: str
    title: str
    url: str
    description: str | None = None
    price: int | None = None
    currency: str | None = None
    seller: str | None = None
    location: str | None = None
    image_url: str | None = None
    condition: str | None = None
    created_at: datetime | None = None
