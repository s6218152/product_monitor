from __future__ import annotations

from dataclasses import dataclass

from app.collectors.marketplace.client import MarketplaceCollector
from app.database.repository import ListingRepository
from app.products.normalizer import normalize_marketplace
from app.products.targets import TARGET_LOCATIONS
from app.products.target_filter import matches_capacity_price
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

    def run(self) -> MonitorResult:
        listings = [normalize_marketplace(item) for item in self._collector.search("iPhone 17 Pro Max")]
        results = self._repository.save_many(listings)
        reasons = Counter(result.rejection_reason or "matched" for result in results)
        logging.getLogger(__name__).info("Marketplace filter counts: %s", dict(reasons))
        matches = [result for result in results if result.is_eligible]
        return MonitorResult(found=len(matches), new=sum(result.is_new for result in matches))
