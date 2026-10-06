from __future__ import annotations

import argparse
import logging
from pathlib import Path
from collections.abc import Sequence

from app.collectors.groups.client import FixtureGroupCollector
from app.collectors.marketplace.client import FixtureMarketplaceCollector
from app.collectors.marketplace.playwright_client import PlaywrightMarketplaceCollector
from app.config import load_settings
from app.database.repository import ListingRepository
from app.monitors.group_monitor import GroupMonitor
from app.monitors.marketplace_monitor import MarketplaceMonitor
from app.notifications.console import notify
from app.notifications.telegram import format_listings, send_html
from app.products.targets import TARGET_LOCATIONS
from app.products.target_filter import matches_capacity_price


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor Facebook products")
    subparsers = parser.add_subparsers(dest="command", required=True)
    marketplace = subparsers.add_parser("marketplace")
    marketplace_source = marketplace.add_mutually_exclusive_group(required=True)
    marketplace_source.add_argument("--fixture", type=Path)
    marketplace_source.add_argument("--live", action="store_true")
    marketplace.add_argument("--database", type=Path)
    groups = subparsers.add_parser("groups")
    groups.add_argument("--fixture", type=Path, required=True)
    groups.add_argument("--database", type=Path)
    subparsers.add_parser("marketplace-login")
    telegram = subparsers.add_parser("telegram", help="輸出 Telegram HTML 格式")
    telegram.add_argument("--limit", type=int, default=10)
    telegram.add_argument("--database", type=Path)
    telegram.add_argument("--send", action="store_true", help="發送至 .env 設定的 Telegram chat")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    logging.basicConfig(level=settings.log_level)
    if args.command == "marketplace-login":
        try:
            PlaywrightMarketplaceCollector(settings.facebook_profile_dir).login()
            return 0
        except (OSError, RuntimeError) as error:
            logging.error("Facebook login setup failed: %s", error)
            return 1
    database_path = args.database or settings.database_path
    try:
        with ListingRepository(database_path) as repository:
            if args.command == "telegram":
                candidates = repository.list_recent(
                    None,
                    TARGET_LOCATIONS,
                    only_unnotified=args.send,
                )
                matches = [
                    listing for listing in candidates
                    if matches_capacity_price(
                        f"{listing['title']} {listing['description'] or ''}",
                        listing["price"],
                    )
                ][:args.limit]
                if args.send:
                    if not matches:
                        print("No new Telegram listings")
                        return 0
                    sent_messages = 0
                    for listing in matches:
                        sent_messages += send_html(
                            settings.telegram_bot_token or "",
                            settings.telegram_chat_id or "",
                            format_listings([listing]),
                        )
                        repository.mark_notified(listing["id"])
                    print(f"Sent {len(matches)} listing(s) in {sent_messages} Telegram message(s)")
                else:
                    print(format_listings(matches))
                return 0
            if args.command == "marketplace":
                collector = (
                    PlaywrightMarketplaceCollector(
                        settings.facebook_profile_dir,
                        headless=settings.facebook_headless,
                        max_scrolls=settings.marketplace_max_scrolls,
                    )
                    if args.live
                    else FixtureMarketplaceCollector(args.fixture)
                )
                result = MarketplaceMonitor(collector, repository).run()
            else:
                result = GroupMonitor(FixtureGroupCollector(args.fixture), repository).run()
        notify(result)
        return 0
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        logging.error("Monitor failed: %s", error)
        return 1
