from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.collectors.groups.models import RawGroupPost
from app.collectors.marketplace.models import RawMarketplaceListing
from app.database.repository import ListingRepository
from app.monitors.group_monitor import GroupMonitor
from app.monitors.marketplace_monitor import MarketplaceMonitor


@pytest.mark.parametrize("source", ["marketplace", "group"])
def test_observed_ineligible_listing_replaces_stale_notification(
    tmp_path: Path, source: str
) -> None:
    class Collector:
        price = 32_000

        def search(self, query: str) -> list[RawMarketplaceListing]:
            del query
            return [RawMarketplaceListing(
                source_id="same", title="iPhone 17 Pro Max 256G", description=None,
                price=self.price, currency="TWD", seller=None, location="新竹縣",
                url="https://test/item", image_url=None, condition=None,
                created_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
            )]

        def posts(self) -> list[RawGroupPost]:
            return [RawGroupPost(
                source_id="same", group_id="test-group", text=f"iPhone 17 Pro Max 256G 新竹縣 售價 {self.price}",
                author=None, url="https://test/item", image_url=None,
                created_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
            )]

    collector = Collector()
    with ListingRepository(tmp_path / "test.db") as repository:
        monitor = MarketplaceMonitor(collector, repository) if source == "marketplace" else GroupMonitor(collector, repository)
        assert monitor.run().new == 1
        collector.price = 33_000
        result = monitor.run()
        assert (result.found, result.new) == (0, 0)
        row = repository.get(source, "same")
        assert row["price"] == 33_000
        assert row["eligible"] == 0
        assert repository.list_recent(only_unnotified=True, only_eligible=True) == []
        collector.price = 31_000
        result = monitor.run()
        assert (result.found, result.new) == (1, 0)
        assert len(repository.list_recent(only_unnotified=True, only_eligible=True)) == 1
