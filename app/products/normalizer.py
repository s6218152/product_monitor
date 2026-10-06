from __future__ import annotations

from app.collectors.groups.models import RawGroupPost
from app.collectors.marketplace.models import RawMarketplaceListing
from app.database.models import ProductListing, utc_now
from app.products.iphone_parser import parse_iphone
from app.products.location_parser import parse_location
from app.products.price_parser import parse_price


def normalize_marketplace(raw: RawMarketplaceListing) -> ProductListing:
    content = " ".join(filter(None, (raw.title, raw.description)))
    return ProductListing(
        source="marketplace", source_id=raw.source_id, title=raw.title,
        description=raw.description, price=raw.price or parse_price(" ".join(filter(None, (raw.title, raw.description)))),
        currency=raw.currency or "TWD", seller=raw.seller,
        location=parse_location(content) or parse_location(raw.location or "") or raw.location,
        url=raw.url, image_url=raw.image_url, condition=raw.condition,
        created_at=raw.created_at, first_seen_at=utc_now(),
    )


def normalize_group(raw: RawGroupPost) -> ProductListing:
    details = parse_iphone(raw.text)
    title = details.model or raw.text.splitlines()[0][:120]
    return ProductListing(
        source="group", source_id=raw.source_id, title=title, description=raw.text,
        price=details.price, currency="TWD", seller=raw.author,
        location=details.location,
        url=raw.url, image_url=raw.image_url,
        condition=None, created_at=raw.created_at, first_seen_at=utc_now(),
    )
