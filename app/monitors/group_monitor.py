from __future__ import annotations

from app.collectors.groups.client import GroupCollector
from app.database.repository import ListingRepository
from app.products.matcher import KeywordMatcher
from app.products.normalizer import normalize_group
from .marketplace_monitor import MonitorResult
from app.products.target_filter import rejection_reason
from collections import Counter
import logging


class GroupMonitor:
    def __init__(self, collector: GroupCollector, repository: ListingRepository) -> None:
        self._collector = collector
        self._repository = repository
        self._matcher = KeywordMatcher(
            ("iPhone 17 Pro Max", "iPhone17 Pro Max", "iPhone17ProMax"),
            ("徵", "收購", "求購"),
        )

    def run(self) -> MonitorResult:
        listings = [normalize_group(post) for post in self._collector.posts()]
        reasons = Counter(rejection_reason(x.description or x.title, x.price, x.location) or "matched" for x in listings)
        logging.getLogger(__name__).info("Groups filter counts: %s", dict(reasons))
        matches = [x for x in listings if rejection_reason(x.description or x.title, x.price, x.location) is None]
        new_count = sum(self._repository.save(listing).is_new for listing in matches)
        return MonitorResult(found=len(matches), new=new_count)
