from __future__ import annotations

from dataclasses import dataclass

from app.collectors.marketplace.client import MarketplaceCollector
from app.database.repository import ListingRepository
from app.products.matcher import KeywordMatcher
from app.products.normalizer import normalize_marketplace
from app.products.targets import TARGET_LOCATIONS
from app.products.target_filter import matches_capacity_price
from app.products.target_filter import rejection_reason
from collections import Counter
import logging


@dataclass(frozen=True, slots=True)
class MonitorResult:
    found: int
    new: int

    @property
    def existing(self) -> int:
        return self.found - self.new


class MarketplaceMonitor:
    def __init__(self, collector: MarketplaceCollector, repository: ListingRepository) -> None:
        self._collector = collector
        self._repository = repository
        self._matcher = KeywordMatcher(
            ("iPhone 17 Pro Max", "iPhone17 Pro Max", "iPhone17ProMax"),
            ("徵", "收購", "求購", "租", "出租", "保護殼", "手機殼", "殼", "維修", "零件"),
        )

    def run(self) -> MonitorResult:
        listings = [normalize_marketplace(item) for item in self._collector.search("iPhone 17 Pro Max")]
        reasons = Counter(rejection_reason(f"{x.title} {x.description or ''}", x.price, x.location) or "matched" for x in listings)
        logging.getLogger(__name__).info("Marketplace filter counts: %s", dict(reasons))
        matches = [
            listing for listing in listings
            if rejection_reason(f"{listing.title} {listing.description or ''}", listing.price, listing.location) is None
        ]
        new_count = sum(self._repository.save(listing).is_new for listing in matches)
        return MonitorResult(found=len(matches), new=new_count)
