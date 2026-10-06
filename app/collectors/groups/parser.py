from __future__ import annotations

from typing import Any
from datetime import datetime

from .models import RawGroupPost


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def parse_post(data: dict[str, Any]) -> RawGroupPost:
    return RawGroupPost(
        source_id=str(data["id"]), group_id=str(data.get("group_id", "unknown")),
        text=str(data["text"]), url=str(data["url"]), author=data.get("author"),
        image_url=data.get("image_url"), created_at=_parse_datetime(data.get("created_at")),
    )
