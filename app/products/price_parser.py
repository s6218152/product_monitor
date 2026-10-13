from __future__ import annotations

import re
from decimal import Decimal
from .text import normalize_text


_MARKED_PRICE = re.compile(
    r"(?:售價?|價格|NT\$|TWD|\$)\s*[:：]?\s*"
    r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(萬|千|K)?"
    r"(?![\d,.])(?!\s*(?:GB?|TB|%))",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<![\d,])(\d{1,3}(?:,\d{3})+|\d{4,7})(?![\d,])")


def _sale_text(text: str) -> str:
    return re.sub(
        r"(?:原價|購入(?:價格|價)?|購買(?:價格|價)?)\s*[:：]?\s*[\d,.]+(?:萬|千|K)?",
        "", normalize_text(text), flags=re.I,
    )


def _price_value(match: re.Match) -> int | None:
    amount = Decimal(match.group(1).replace(",", ""))
    unit = (match.group(2) or "").upper()
    amount *= {"萬": 10000, "千": 1000, "K": 1000}.get(unit, 1)
    return int(amount) if amount == int(amount) and 0 < amount <= 200_000 else None


def sale_prices(text: str) -> set[int]:
    return {value for match in _MARKED_PRICE.finditer(_sale_text(text))
            if (value := _price_value(match)) is not None}


def parse_price(text: str) -> int | None:
    text = _sale_text(text)
    for marked in _MARKED_PRICE.finditer(text):
        value = _price_value(marked)
        if value is not None:
            return value

    for match in _NUMBER.finditer(text):
        value = int(match.group(1).replace(",", ""))
        suffix = text[match.end(): match.end() + 3].lstrip().upper()
        if suffix.startswith(("G", "GB", "%")) or 2000 <= value <= 2099 or value > 200_000:
            continue
        return value
    return None
