from __future__ import annotations

from typing import Any
from datetime import datetime

from .models import RawMarketplaceListing


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def parse_listing(data: dict[str, Any]) -> RawMarketplaceListing:
    return RawMarketplaceListing(
        source_id=str(data["id"]), title=str(data["title"]), url=str(data["url"]),
        description=data.get("description"), price=data.get("price"),
        currency=data.get("currency"), seller=data.get("seller"),
        location=data.get("location"), image_url=data.get("image_url"),
        condition=data.get("condition"), created_at=_parse_datetime(data.get("created_at")),
    )
