from __future__ import annotations

from app.collectors.groups.client import GroupCollector
from app.database.repository import ListingRepository
from app.products.normalizer import normalize_group
from .marketplace_monitor import MonitorResult
from collections import Counter
import logging


class GroupMonitor:
    def __init__(self, collector: GroupCollector, repository: ListingRepository) -> None:
        self._collector = collector
        self._repository = repository

    def run(self) -> MonitorResult:
        listings = [normalize_group(post) for post in self._collector.posts()]
        results = self._repository.save_many(listings)
        reasons = Counter(result.rejection_reason or "matched" for result in results)
        logging.getLogger(__name__).info("Groups filter counts: %s", dict(reasons))
        matches = [result for result in results if result.is_eligible]
        return MonitorResult(found=len(matches), new=sum(result.is_new for result in matches))
