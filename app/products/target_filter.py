from __future__ import annotations

from .storage_parser import parse_storage_gb
import re
from .matcher import KeywordMatcher
from .targets import TARGET_LOCATIONS


MAX_PRICE_BY_STORAGE = {256: 32_000, 512: 37_000}


def matches_capacity_price(text: str, price: int | None) -> bool:
    storage = parse_storage_gb(text)
    return price is not None and 0 < price and storage in MAX_PRICE_BY_STORAGE and price <= MAX_PRICE_BY_STORAGE[storage]


def rejection_reason(text: str, price: int | None, location: str | None) -> str | None:
    if not KeywordMatcher(("iPhone 17 Pro Max",)).matches(text):
        return "model"
    if re.search(r"(?:^|\n)\s*(?:徵|收購|求購|出租)|(?:售|賣|販售)\s*(?:保護殼|手機殼|零件)|(?:維修服務|維修報價)", text):
        return "wanted_or_accessory"
    capacities = set(re.findall(r"(?<!\d)(128|256|512)\s*G(?:B)?\b", text, re.I))
    if len(capacities) > 1:
        return "multiple_products"
    if location not in TARGET_LOCATIONS:
        return "location"
    if not matches_capacity_price(text, price):
        return "capacity_or_price"
    return None
