from __future__ import annotations

from .storage_parser import parse_storage_gb


MAX_PRICE_BY_STORAGE = {256: 32_000, 512: 37_000}


def matches_capacity_price(text: str, price: int | None) -> bool:
    storage = parse_storage_gb(text)
    return price is not None and storage in MAX_PRICE_BY_STORAGE and price <= MAX_PRICE_BY_STORAGE[storage]
