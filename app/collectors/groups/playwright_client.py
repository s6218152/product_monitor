from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

from app.collectors.marketplace.playwright_client import parse_posted_at
from .models import RawGroupPost


LOGGER = logging.getLogger(__name__)
_POST_URL = re.compile(r"/groups/([^/]+)/(?:posts|permalink)/(\d+)")


def snapshot(page: object) -> list[dict]:
    return page.locator('div[role="feed"] div[role="article"]').evaluate_all("""articles => articles.map(article => {
        const links = [...article.querySelectorAll('a[href]')];
        const link = links.find(a => /\\/groups\\/[^/]+\\/(posts|permalink)\\/\\d+/.test(a.href));
        const body = article.querySelector('[data-ad-preview="message"], [data-ad-comet-preview="message"]');
        const timed = article.querySelector('[data-utime], time[datetime]');
        return {text: body ? body.innerText : '', href: link ? link.href : '', author: null,
            imageUrl: null, timestamp: timed ? (timed.getAttribute('data-utime') || timed.getAttribute('datetime')) : null,
            timeLabel: link ? (link.getAttribute('aria-label') || link.innerText) : null};
    })""")  # type: ignore[attr-defined]


def _canonical_url(href: str) -> str:
    absolute = urljoin("https://www.facebook.com", href)
    parts = urlsplit(absolute)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def post_from_article(
    text: str,
    href: str,
    *,
    author: str | None = None,
    image_url: str | None = None,
    timestamp: str | None = None,
    time_label: str | None = None,
    now: datetime | None = None,
) -> RawGroupPost | None:
    match = _POST_URL.search(href)
    content = text.strip()
    if not match or not content:
        return None
    created_at: datetime | None = None
    if timestamp:
        try:
            created_at = (
                datetime.fromtimestamp(int(timestamp), timezone.utc)
                if timestamp.isdigit()
                else datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            )
        except (ValueError, OverflowError):
            pass
    if created_at is None and time_label:
        created_at = parse_posted_at(time_label, now)
        absolute = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?:.*?(\d{1,2}):(\d{2}))?', time_label)
        if created_at is None and absolute:
            from zoneinfo import ZoneInfo
            try:
                year, month, day, hour, minute = absolute.groups()
                created_at = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0), tzinfo=ZoneInfo('Asia/Taipei'))
            except ValueError:
                pass
    return RawGroupPost(
        source_id=match.group(2),
        group_id=match.group(1),
        text=content,
        url=_canonical_url(href),
        author=author.strip() if author and author.strip() else None,
        image_url=image_url,
        created_at=created_at,
    )


class PlaywrightGroupCollector:
    def __init__(
        self,
        profile_dir: Path,
        group_urls: tuple[str, ...],
        *,
        headless: bool = False,
        max_scrolls: int = 3,
    ) -> None:
        self._profile_dir = profile_dir
        self._group_urls = group_urls
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

    def posts(self) -> list[RawGroupPost]:
        if not self._group_urls:
            raise ValueError("FACEBOOK_GROUP_URLS is empty")
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        found: dict[str, RawGroupPost] = {}
        with self._playwright() as playwright:  # type: ignore[attr-defined]
            context = playwright.chromium.launch_persistent_context(
                self._profile_dir, headless=self._headless, locale="zh-TW"
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                for group_url in self._group_urls:
                    started = time.monotonic()
                    before = len(found)
                    try:
                        page.goto(group_url.rstrip('/') + '/?sorting_setting=CHRONOLOGICAL', wait_until="domcontentloaded", timeout=60_000)
                        if "login" in page.url or page.locator('input[name="email"]').count():
                            raise RuntimeError("Facebook 尚未登入，請先執行：python main.py marketplace-login")
                        page.wait_for_timeout(2_000)
                        body_text = page.locator('body').inner_text(timeout=5000)
                        if any(message in body_text for message in ('此內容目前無法查看', '內容目前無法顯示', '加入社團以查看', 'This content isn’t available')):
                            LOGGER.warning('Group inaccessible or membership required: %s', group_url)
                            continue
                        if page.get_by_text('新貼文', exact=True).count() == 0:
                            LOGGER.warning('Group chronological sorting not confirmed: %s', group_url)
                        for _ in range(self._max_scrolls + 1):
                            for label in ("查看更多", "顯示更多"):
                                controls = page.get_by_text(label, exact=True)
                                for index in range(min(controls.count(), 15)):
                                    try:
                                        controls.nth(index).click(timeout=300)
                                    except Exception:
                                        pass
                            for article in snapshot(page):
                                post = post_from_article(article['text'], article['href'], timestamp=article['timestamp'], time_label=article['timeLabel'])
                                if post:
                                    found[f'{post.group_id}:{post.source_id}'] = post
                            page.mouse.wheel(0, 2_000)
                            page.wait_for_timeout(1_000)
                        for label in ("查看更多", "顯示更多"):
                            controls = page.get_by_text(label, exact=True)
                            for index in range(min(controls.count(), 30)):
                                try:
                                    controls.nth(index).click(timeout=500)
                                except Exception:
                                    pass
                        articles = page.locator('div[role="feed"] div[role="article"]').evaluate_all(
                            """articles => articles.map(article => {
                                const links = [...article.querySelectorAll('a[href]')];
                                const postLink = links.find(a => /\\/groups\\/[^/]+\\/(posts|permalink)\\/\\d+/.test(a.href));
                                const authorLink = links.find(a => /facebook\\.com\\/(profile\\.php|[^/?#]+)($|\\?)/.test(a.href)
                                    && !/\\/groups\\//.test(a.href));
                                const timed = article.querySelector('[data-utime], time[datetime]');
                                const timeLink = links.find(a => a.getAttribute('aria-label') && a.href === (postLink && postLink.href));
                                return {
                                    text: (article.querySelector('[data-ad-preview="message"], [data-ad-comet-preview="message"]') || {}).innerText || '', href: postLink ? postLink.href : '',
                                    author: authorLink ? authorLink.innerText : null,
                                    imageUrl: (article.querySelector('img[src]') || {}).src || null,
                                    timestamp: timed ? (timed.getAttribute('data-utime') || timed.getAttribute('datetime')) : null,
                                    timeLabel: timeLink ? timeLink.getAttribute('aria-label') : null
                                };
                            })"""
                        )
                        for article in articles:
                            post = post_from_article(
                                article["text"], article["href"], author=article["author"],
                                image_url=article["imageUrl"], timestamp=article["timestamp"],
                                time_label=article["timeLabel"],
                            )
                            if post:
                                found[f"{post.group_id}:{post.source_id}"] = post
                    except RuntimeError:
                        raise
                    except Exception as error:
                        LOGGER.warning("Could not read Facebook group %s: %s", group_url, error)
                    finally:
                        LOGGER.info("Group %s posts=%d elapsed=%.1fs missing_time=%d sort=requested_chronological", group_url, len(found)-before, time.monotonic()-started, sum(p.created_at is None for p in found.values()))
            finally:
                context.close()
        LOGGER.info("Facebook groups yielded %d unique posts", len(found))
        return list(found.values())
