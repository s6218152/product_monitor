from __future__ import annotations

from app.collectors.groups.client import GroupCollector
from app.database.repository import ListingRepository
from app.products.matcher import KeywordMatcher
from app.products.normalizer import normalize_group
from .marketplace_monitor import MonitorResult


class GroupMonitor:
    def __init__(self, collector: GroupCollector, repository: ListingRepository) -> None:
        self._collector = collector
        self._repository = repository
        self._matcher = KeywordMatcher(
            ("iPhone 17 Pro Max", "iPhone17 Pro Max", "iPhone17ProMax"),
            ("徵", "收購", "求購"),
        )

    def run(self) -> MonitorResult:
        matches = [post for post in self._collector.posts() if self._matcher.matches(post.text)]
        new_count = sum(self._repository.save(normalize_group(post)).is_new for post in matches)
        return MonitorResult(found=len(matches), new=new_count)
