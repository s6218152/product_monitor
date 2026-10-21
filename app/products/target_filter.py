from __future__ import annotations

from .storage_parser import parse_storage_gb, storage_values
import re
from .matcher import KeywordMatcher
from .targets import TARGET_LOCATIONS
from .price_parser import sale_prices
from .text import normalize_text


MAX_PRICE_BY_STORAGE = {256: 32_000, 512: 37_000}
_MATCHER = KeywordMatcher(("iPhone 17 Pro Max",))
_MODELS = re.compile(r"iphone\s*\d+\s*(?:(?:pro\s*max|pro|plus|mini|air))?", re.I)


def matches_capacity_price(text: str, price: int | None) -> bool:
    storage = parse_storage_gb(text)
    return price is not None and 0 < price and storage in MAX_PRICE_BY_STORAGE and price <= MAX_PRICE_BY_STORAGE[storage]


def rejection_reason(text: str, price: int | None, location: str | None) -> str | None:
    text = normalize_text(text)
    from app.monitor_config import read_config
    custom = read_config()
    if custom is not None and custom['products']:
        for product in custom["products"]:
            if KeywordMatcher((product["keyword"],)).matches(text):
                if price is not None and 0 < price <= product["max_price"]:
                    return None
        return "custom_product_or_price"
    if not _MATCHER.matches(text):
        return "model"
    if re.search(r"(?<!非)(?<!不)(?:收購|求購|徵求|出租)|(?:^|[\s【\[(])徵", text):
        return "wanted_or_accessory"
    subject = re.sub(r"(?:附(?:贈)?|贈送|送)[^，。;\n]{0,20}?(?:保護殼|手機殼|零件)", "", text)
    subject = re.sub(r"(?:保護殼|手機殼|零件)\s*(?:附贈|贈送|隨附)", "", subject)
    subject = re.sub(r"(?:裝|套|使用|搭配|附有|附上|附帶|含)\s*(?:保護殼|手機殼)", "", subject)
    subject = re.sub(r"(?:無|沒有|未|不曾)(?:維修|更換零件)", "", subject)
    if re.search(r"保護殼|手機殼|零件|維修服務|維修報價", subject):
        return "wanted_or_accessory"
    models = {re.sub(r"\s+", "", match.group()).casefold() for match in _MODELS.finditer(text)}
    if len(storage_values(text)) > 1 or len(models) > 1 or len(sale_prices(text)) > 1:
        return "multiple_products"
    if location not in TARGET_LOCATIONS:
        return "location"
    if not matches_capacity_price(text, price):
        return "capacity_or_price"
    return None
