from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .models import RawMarketplaceListing
from .parser import parse_listing


class MarketplaceCollector(Protocol):
    def search(self, query: str) -> list[RawMarketplaceListing]: ...


class FixtureMarketplaceCollector:
    def __init__(self, fixture_path: Path) -> None:
        self._fixture_path = fixture_path

    def search(self, query: str) -> list[RawMarketplaceListing]:
        del query
        payload = json.loads(self._fixture_path.read_text(encoding="utf-8"))
        records = payload.get("listings", payload) if isinstance(payload, dict) else payload
        return [parse_listing(item) for item in records]
