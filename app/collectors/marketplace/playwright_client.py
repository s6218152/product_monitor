from __future__ import annotations

import logging
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from urllib.parse import quote_plus, urljoin, urlsplit, urlunsplit

from app.products.price_parser import parse_price
from .models import RawMarketplaceListing


LOGGER = logging.getLogger(__name__)
_ITEM_ID = re.compile(r"/marketplace/item/(\d+)")
_RELATIVE_TIME = re.compile(r"(\d+)\s*(分鐘|小時|天|週)前")


def _canonical_url(href: str) -> str:
    absolute = urljoin("https://www.facebook.com", href)
    parts = urlsplit(absolute)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def parse_posted_at(text: str, now: datetime | None = None) -> datetime | None:
    reference = now or datetime.now(timezone.utc)
    match = _RELATIVE_TIME.search(text)
    if not match:
        return reference if "剛剛" in text else None
    amount = int(match.group(1))
    unit = match.group(2)
    delta = {
        "分鐘": timedelta(minutes=amount),
        "小時": timedelta(hours=amount),
        "天": timedelta(days=amount),
        "週": timedelta(weeks=amount),
    }[unit]
    return reference - delta


def parse_creation_time(html: str, source_id: str) -> datetime | None:
    pattern = re.compile(
        rf'"id":"{re.escape(source_id)}".{{0,4000}}?"creation_time":(\d+)',
        re.DOTALL,
    )
    match = pattern.search(html)
    return datetime.fromtimestamp(int(match.group(1)), timezone.utc) if match else None


def parse_facebook_location(html: str, source_id: str) -> str | None:
    pattern = re.compile(
        rf'"id":"{re.escape(source_id)}".{{0,5000}}?'
        r'"location_text":\{"text":"((?:\\.|[^"\\])*)"',
        re.DOTALL,
    )
    match = pattern.search(html)
    if not match:
        return None
    value = json.loads(f'"{match.group(1)}"')
    return re.sub(r"\s*,\s*台灣$", "", value).strip() or None


def parse_facebook_description(html: str, source_id: str) -> str | None:
    pattern = re.compile(
        rf'"id":"{re.escape(source_id)}".{{0,20000}}?'
        r'"redacted_description":\{"text":"((?:\\.|[^"\\])*)"',
        re.DOTALL,
    )
    match = pattern.search(html)
    if not match:
        return None
    return json.loads(f'"{match.group(1)}"').strip() or None


def _matches_query(item: RawMarketplaceListing, query: str) -> bool:
    compact_query = re.sub(r"\s+", "", query).casefold()
    compact_text = re.sub(r"\s+", "", f"{item.title} {item.description or ''}").casefold()
    return compact_query in compact_text


def listing_from_link(href: str, text: str, aria_label: str | None = None) -> RawMarketplaceListing | None:
    match = _ITEM_ID.search(href)
    if not match:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = aria_label.strip() if aria_label and aria_label.strip() else next(
        (line for line in lines if parse_price(line) is None),
        lines[0] if lines else "Facebook Marketplace listing",
    )
    return RawMarketplaceListing(
        source_id=match.group(1),
        title=title,
        description=text.strip() or None,
        price=parse_price(text),
        currency="TWD",
        url=_canonical_url(href),
    )


class PlaywrightMarketplaceCollector:
    def __init__(self, profile_dir: Path, *, headless: bool = False, max_scrolls: int = 3) -> None:
        self._profile_dir = profile_dir
        self._headless = headless
        self._max_scrolls = max_scrolls

    @staticmethod
    def _playwright() -> object:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install -e '.[facebook]' && playwright install chromium"
            ) from error
        return sync_playwright()

    def login(self) -> None:
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        with self._playwright() as playwright:  # type: ignore[attr-defined]
            context = playwright.chromium.launch_persistent_context(
                self._profile_dir, headless=False, locale="zh-TW"
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.facebook.com/marketplace/", wait_until="domcontentloaded")
            input("請在瀏覽器完成 Facebook 登入並開啟 Marketplace，完成後回到終端機按 Enter：")
            context.close()

    def search(self, query: str) -> list[RawMarketplaceListing]:
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        url = f"https://www.facebook.com/marketplace/search/?query={quote_plus(query)}"
        with self._playwright() as playwright:  # type: ignore[attr-defined]
            context = playwright.chromium.launch_persistent_context(
                self._profile_dir, headless=self._headless, locale="zh-TW"
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                if "login" in page.url or page.locator('input[name="email"]').count():
                    raise RuntimeError("Facebook 尚未登入，請先執行：python main.py marketplace-login")
                page.wait_for_timeout(2_000)
                for _ in range(self._max_scrolls):
                    page.mouse.wheel(0, 2_000)
                    page.wait_for_timeout(1_000)
                found: dict[str, RawMarketplaceListing] = {}
                links = page.locator('a[href*="/marketplace/item/"]')
                for index in range(links.count()):
                    link = links.nth(index)
                    item = listing_from_link(
                        link.get_attribute("href") or "",
                        link.inner_text(timeout=3_000),
                        link.get_attribute("aria-label"),
                    )
                    if item:
                        found[item.source_id] = item
                for source_id, item in tuple(found.items()):
                    if not _matches_query(item, query):
                        continue
                    posted_at, facebook_location, description = self._read_details(
                        page, item.url, item.source_id
                    )
                    found[source_id] = replace(
                        item,
                        created_at=posted_at,
                        location=facebook_location,
                        description=description or item.description,
                    )
                LOGGER.info("Marketplace page yielded %d unique item links", len(found))
                return list(found.values())
            finally:
                context.close()

    @staticmethod
    def _read_details(
        page: object, url: str, source_id: str
    ) -> tuple[datetime | None, str | None, str | None]:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)  # type: ignore[attr-defined]
            page.wait_for_timeout(1_000)  # type: ignore[attr-defined]
            html = page.content()  # type: ignore[attr-defined]
            embedded_time = parse_creation_time(html, source_id)
            location = parse_facebook_location(html, source_id)
            description = parse_facebook_description(html, source_id)
            if embedded_time:
                return embedded_time, location, description
            labels = page.locator("abbr[aria-label]")  # type: ignore[attr-defined]
            now = datetime.now(timezone.utc)
            for index in range(labels.count()):
                value = labels.nth(index).get_attribute("aria-label") or ""
                posted_at = parse_posted_at(value, now)
                if posted_at:
                    return posted_at, location, description
            LOGGER.warning("No post time found on Marketplace item: %s", url)
        except Exception as error:
            LOGGER.warning("Could not read Marketplace post time from %s: %s", url, error)
        return None, None, None
