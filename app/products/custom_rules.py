"""Conservative, deterministic assessment of user-configured products."""
from dataclasses import dataclass
import re
from app.monitor_config import read_config
from .matcher import KeywordMatcher
from .text import normalize_text

_PHONE_MODEL = re.compile(r'iphone\s*\d+\s*(?:pro\s*max|pro|plus|mini|air)?', re.I)


@dataclass(frozen=True)
class Assessment:
    status: str
    price: int | None
    reason: str | None = None


def listing_text(title: str | None, description: str | None) -> str:
    title_str = (title or '').strip()
    desc_str = (description or '').strip()
    if desc_str and title_str and desc_str.startswith(title_str):
        return desc_str
    return f'{title_str}\n{desc_str}'.strip()


def _exclude_gift_accessories(text: str) -> str:
    subject = re.sub(r'(?:附(?:贈)?|贈送|送)[^，。;\n]{0,20}?(?:保護殼|手機殼|零件)', '', text)
    subject = re.sub(r'(?:保護殼|手機殼|零件)\s*(?:附贈|贈送|隨附)', '', subject)
    subject = re.sub(r'(?:裝|套|使用|搭配|附有|附上|附帶|含)\s*(?:保護殼|手機殼)', '', subject)
    return re.sub(r'(?:無|沒有|未|不曾)(?:維修|更換零件)', '', subject)


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
        actual = price
        last_price = actual
        ambiguous = actual is None or actual <= 0
        if kind == 'phone':
            from .storage_parser import storage_values
            from .price_parser import sale_prices
            capacities = storage_values(text)
            models = {re.sub(r'\s+', '', match.group()).casefold() for match in _PHONE_MODEL.finditer(text)}
            expected_models = {re.sub(r'\s+', '', match.group()).casefold()
                               for match in _PHONE_MODEL.finditer(product['keyword'])}
            ambiguous = ambiguous or len(capacities) != 1 or len(sale_prices(text)) > 1
            if re.search(r'保護殼|手機殼|零件|維修服務|維修報價', _exclude_gift_accessories(text)):
                continue
            if expected_models and (models != expected_models):
                continue
            if not expected_models and len(models) > 1:
                continue
            if product.get('capacity_gb') is not None and capacities != {product['capacity_gb']}:
                continue
            regions = product.get('regions', [])
            if regions and (not location or not any(location == region or location.startswith(region) for region in regions)):
                continue
        if not ambiguous:
            if actual <= product['max_price']:
                return Assessment('matched', actual)
        elif product.get('notify_uncertain', False):
            pending = Assessment('pending', actual, '價格或必要資訊待確認')
    return pending or Assessment('rejected', last_price, 'custom_product_or_price')
