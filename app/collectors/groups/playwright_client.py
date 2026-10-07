from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from app.collectors.marketplace.playwright_client import parse_posted_at
from .models import RawGroupPost


LOGGER = logging.getLogger(__name__)
_POST_URL = re.compile(r"/groups/([^/]+)/(?:posts|permalink)/(\d+)")


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
                    try:
                        page.goto(group_url, wait_until="domcontentloaded", timeout=60_000)
                        if "login" in page.url or page.locator('input[name="email"]').count():
                            raise RuntimeError("Facebook 尚未登入，請先執行：python main.py marketplace-login")
                        page.wait_for_timeout(2_000)
                        for _ in range(self._max_scrolls):
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
                                    text: article.innerText || '', href: postLink ? postLink.href : '',
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
                context.close()
        LOGGER.info("Facebook groups yielded %d unique posts", len(found))
        return list(found.values())
