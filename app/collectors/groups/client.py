from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .models import RawGroupPost
from .parser import parse_post


class GroupCollector(Protocol):
    def posts(self) -> list[RawGroupPost]: ...


class FixtureGroupCollector:
    def __init__(self, fixture_path: Path) -> None:
        self._fixture_path = fixture_path

    def posts(self) -> list[RawGroupPost]:
        payload = json.loads(self._fixture_path.read_text(encoding="utf-8"))
        records = payload.get("posts", payload) if isinstance(payload, dict) else payload
        return [parse_post(item) for item in records]
