from __future__ import annotations

import re


_MARKED_PRICE = re.compile(
    r"(?:售價?|價格|NT\$|TWD|\$)\s*[:：]?\s*(\d{1,3}(?:,\d{3})+|\d{4,7})(?!\s*(?:GB?|%))",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<![\d,])(\d{1,3}(?:,\d{3})+|\d{4,7})(?![\d,])")


def parse_price(text: str) -> int | None:
    marked = _MARKED_PRICE.search(text)
    if marked:
        return int(marked.group(1).replace(",", ""))

    for match in _NUMBER.finditer(text):
        value = int(match.group(1).replace(",", ""))
        suffix = text[match.end(): match.end() + 3].lstrip().upper()
        if suffix.startswith(("G", "GB", "%")) or 2000 <= value <= 2099:
            continue
        return value
    return None
