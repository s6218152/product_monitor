from __future__ import annotations

from dataclasses import dataclass

from app.collectors.marketplace.client import MarketplaceCollector
from app.database.repository import ListingRepository
from app.products.matcher import KeywordMatcher
from app.products.normalizer import normalize_marketplace
from app.products.targets import TARGET_LOCATIONS
from app.products.target_filter import matches_capacity_price


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
        listings = [
            normalize_marketplace(item)
            for item in self._collector.search("iPhone 17 Pro Max")
            if self._matcher.matches(" ".join(filter(None, (item.title, item.description))))
        ]
        matches = [
            listing for listing in listings
            if listing.location in TARGET_LOCATIONS
            and matches_capacity_price(
                f"{listing.title} {listing.description or ''}", listing.price
            )
        ]
        new_count = sum(self._repository.save(listing).is_new for listing in matches)
        return MonitorResult(found=len(matches), new=new_count)
