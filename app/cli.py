from __future__ import annotations

import argparse
import logging
from pathlib import Path
from collections.abc import Sequence

from app.collectors.groups.client import FixtureGroupCollector
from app.collectors.groups.playwright_client import PlaywrightGroupCollector
from app.collectors.marketplace.client import FixtureMarketplaceCollector
from app.collectors.marketplace.playwright_client import PlaywrightMarketplaceCollector
from app.config import load_settings
from app.database.repository import ListingRepository
from app.monitors.group_monitor import GroupMonitor
from app.monitors.marketplace_monitor import MarketplaceMonitor
from app.notifications.console import notify
from app.notifications.telegram import TelegramError, format_listings, send_html
from app.products.targets import TARGET_LOCATIONS


def _positive_int(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor Facebook products")
    subparsers = parser.add_subparsers(dest="command", required=True)
    marketplace = subparsers.add_parser("marketplace")
    marketplace_source = marketplace.add_mutually_exclusive_group(required=True)
    marketplace_source.add_argument("--fixture", type=Path)
    marketplace_source.add_argument("--live", action="store_true")
    marketplace.add_argument("--database", type=Path)
    groups = subparsers.add_parser("groups")
    groups_source = groups.add_mutually_exclusive_group(required=True)
    groups_source.add_argument("--fixture", type=Path)
    groups_source.add_argument("--live", action="store_true")
    groups.add_argument("--database", type=Path)
    subparsers.add_parser("marketplace-login")
    telegram = subparsers.add_parser("telegram", help="輸出 Telegram HTML 格式")
    telegram.add_argument("--limit", type=_positive_int, default=10)
    telegram.add_argument("--database", type=Path)
    telegram.add_argument("--send", action="store_true", help="發送至 .env 設定的 Telegram chat")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings()
        logging.basicConfig(level=settings.log_level)
    except (OSError, ValueError) as error:
        logging.error("Invalid configuration: %s", error)
        return 1
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
                matches = repository.list_recent(
                    args.limit,
                    TARGET_LOCATIONS,
                    only_unnotified=args.send,
                    only_eligible=True,
                )
                if args.send:
                    if not matches:
                        print("No new Telegram listings")
                        return 0
                    sent_messages = 0
                    sent_listings = 0
                    failures = 0
                    if not settings.telegram_bot_token or not settings.telegram_chat_id:
                        raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
                    for listing in matches:
                        try:
                            sent_messages += send_html(
                                settings.telegram_bot_token,
                                settings.telegram_chat_id,
                                format_listings([listing]),
                            )
                        except (OSError, RuntimeError, ValueError) as error:
                            failures += 1
                            logging.error("Telegram listing_id=%s failed: %s", listing["id"], error)
                            if isinstance(error, TelegramError) and error.status_code in {401, 403}:
                                return 1
                            retry_after = getattr(error, "retry_after", None)
                            repository.mark_notification_failed(
                                listing["id"], str(error), retry_after_seconds=retry_after or 300,
                            )
                            if isinstance(error, TelegramError) and error.status_code == 429:
                                repository.defer_notifications(retry_after or 300)
                                break
                            continue
                        repository.mark_notified(listing["id"], sent_price=listing["price"])
                        sent_listings += 1
                    print(f"Sent {sent_listings} listing(s) in {sent_messages} Telegram message(s)")
                    if failures:
                        print(f"Failed: {failures} listing(s); retained for retry")
                    return 1 if failures else 0
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
                collector = (
                    PlaywrightGroupCollector(
                        settings.facebook_profile_dir,
                        settings.facebook_group_urls,
                        headless=settings.facebook_headless,
                        max_scrolls=settings.groups_max_scrolls,
                    )
                    if args.live
                    else FixtureGroupCollector(args.fixture)
                )
                result = GroupMonitor(collector, repository).run()
        notify(result)
        return 0
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        logging.error("Monitor failed: %s", error)
        return 1
