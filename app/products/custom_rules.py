"""Conservative, deterministic assessment of user-configured products."""
from dataclasses import dataclass
from decimal import Decimal
import re
from app.monitor_config import read_config
from .matcher import KeywordMatcher
from .text import normalize_text


@dataclass(frozen=True)
class Assessment:
    status: str
    price: int | None
    reason: str | None = None


def voucher_price(text):
    text = normalize_text(text)
    amounts = lambda pattern: {int(value.replace(',', '')) for value in re.findall(pattern, text)}
    face = amounts(r'(?:面額|票面)\s*[:：]?\s*\$?\s*(\d[\d,]*)')
    sale = amounts(r'(?:售價|賣價|轉讓價|售)\s*[:：]?\s*\$?\s*(\d[\d,]*)(?![\d,.]|\s*折)')
    ratios = {Decimal(value) for value in re.findall(r'(\d+(?:\.\d+)?)\s*折', text)}
    if len(face) > 1 or len(sale) > 1 or len(ratios) > 1 or re.search(r'(?:共|合計|整批)|(?:[2-9]|[1-9]\d+)\s*張', text):
        return None
    if len(sale) == 1:
        return next(iter(sale)) or None
    if len(face) == 1 and len(ratios) == 1:
        ratio = next(iter(ratios))
        ratio = ratio / (100 if ratio > 10 else 10)
        value = next(iter(face)) * ratio
        return int(value) if 0 < ratio <= 1 and value == int(value) else None
    return None


def assess_custom(text, price, location=None, source=None):
    config = read_config()
    if not config or not config['products']:
        return None
    text = normalize_text(text)
    candidates = [p for p in config['products'] if KeywordMatcher((p['keyword'],)).matches(text)
                  and (source is None or p.get('source', 'both') in ('both', source))]
    if not candidates:
        return Assessment('rejected', price, 'custom_product_or_price')
    if re.search(r'已售出|已售完|售罄|交易完成|(?<!非)(?<!不)(?:收購|求購|徵求|出租)|(?:^|[\s【\[(])徵', text):
        return Assessment('rejected', price, 'wanted_or_sold')
    pending = None
    last_price = price
    for product in candidates:
        kind = product.get('type', 'general')
        actual = voucher_price(text) if kind == 'voucher' else price
        last_price = actual
        ambiguous = actual is None or actual <= 0
        if kind == 'phone':
            from .storage_parser import storage_values
            from .price_parser import sale_prices
            ambiguous = ambiguous or len(storage_values(text)) != 1 or len(sale_prices(text)) > 1
            if re.search(r'保護殼|手機殼|維修服務|維修報價', text):
                continue
        if not ambiguous:
            if actual <= product['max_price']:
                return Assessment('matched', actual)
        elif product.get('notify_uncertain', False):
            pending = Assessment('pending', None if kind == 'voucher' else actual, '價格或必要資訊待確認')
    return pending or Assessment('rejected', last_price, 'custom_product_or_price')
