from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RawGroupPost:
    source_id: str
    group_id: str
    text: str
    url: str
    author: str | None = None
    image_url: str | None = None
    created_at: datetime | None = None
