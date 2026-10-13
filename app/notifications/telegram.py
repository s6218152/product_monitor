from __future__ import annotations

from datetime import datetime
from html import escape
from html.parser import HTMLParser
from sqlite3 import Row
from zoneinfo import ZoneInfo
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.products.storage_parser import format_storage_gb


TAIPEI = ZoneInfo("Asia/Taipei")


class TelegramError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retry_after: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class _HTMLChunks(HTMLParser):
    """Split rendered text while keeping formatting and entities intact."""

    def __init__(self, limit: int):
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.parts: list[str] = []
        self.current = ""
        self.length = 0
        self.stack: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        opening = self.get_starttag_text()
        self.current += opening
        self.stack.append((tag, opening))

    def handle_endtag(self, tag: str) -> None:
        self.current += f"</{tag}>"
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        while data:
            if self.length == self.limit:
                self.flush()
            room = self.limit - self.length
            piece, data = data[:room], data[room:]
            self.current += escape(piece, quote=False)
            self.length += len(piece)

    def flush(self) -> None:
        if self.length:
            self.parts.append(self.current + "".join(f"</{tag}>" for tag, _ in reversed(self.stack)))
        self.current = "".join(opening for _, opening in self.stack)
        self.length = 0


def _html_chunks(message: str, limit: int) -> list[str]:
    parser = _HTMLChunks(limit)
    parser.feed(message)
    parser.close()
    parser.flush()
    return parser.parts


def _format_time(value: str | None) -> str:
    if not value:
        return "未知"
    return datetime.fromisoformat(value).astimezone(TAIPEI).strftime("%Y/%m/%d %H:%M")


def _format_storage(title: str, description: str | None) -> str:
    return format_storage_gb(f"{title} {description or ''}")


def format_listings(listings: list[Row]) -> str:
    if not listings:
        return "🔍 <b>目前沒有商品資料</b>"
    blocks = ["🔔 <b>iPhone 17 Pro Max 商品</b>"]
    for listing in listings:
        url = escape(listing["url"], quote=True)
        price = (
            f"{escape(listing['currency'])} {listing['price']:,}"
            if listing["price"] is not None
            else "價格未提供"
        )
        blocks.append(
            "\n".join((
                "📉 降價通知" if "notified_price" in listing.keys() and listing["notified_price"] is not None and listing["price"] < listing["notified_price"] else "🆕 商品通知",
                f"📱 容量：<b>{_format_storage(listing['title'], listing['description'])}</b>",
                f"💰 {price}",
                f"📍 地區：{escape(listing['location'] or '未提供')}",
                f"🕒 上架：{_format_time(listing['last_seen_at'])}",
                f'🔗 商品連結：<a href="{url}">{url}</a>',
            ))
        )
    return "\n\n".join(blocks)


def _split_message(message: str, limit: int = 4000) -> list[str]:
    if limit < 1:
        raise ValueError("message limit must be at least 1")
    parts: list[str] = []
    current = ""
    for block in message.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        chunks = _html_chunks(candidate, limit)
        if len(chunks) <= 1:
            current = candidate
        else:
            if current:
                parts.append(current)
            block_chunks = _html_chunks(block, limit)
            parts.extend(block_chunks[:-1])
            current = block_chunks[-1] if block_chunks else ""
    if current:
        parts.append(current)
    return parts


def send_html(bot_token: str, chat_id: str, message: str) -> int:
    if not bot_token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
    endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    sent = 0
    for part in _split_message(message):
        payload = json.dumps({
            "chat_id": chat_id,
            "text": part,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }).encode("utf-8")
        request = Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            try:
                result = json.loads(error.read().decode("utf-8"))
            except (ValueError, UnicodeError):
                result = {}
            if not isinstance(result, dict):
                result = {}
            parameters = result.get("parameters") or {}
            retry_after = parameters.get("retry_after") if isinstance(parameters, dict) else None
            raise TelegramError(
                f"Telegram HTTP {error.code}: {result.get('description', 'request rejected')}",
                status_code=error.code,
                retry_after=retry_after if isinstance(retry_after, int) and retry_after > 0 else None,
            ) from error
        except URLError as error:
            raise RuntimeError(f"Could not reach Telegram: {error.reason}") from error
        if not isinstance(result, dict):
            raise TelegramError("Telegram returned an invalid response")
        if not result.get("ok"):
            parameters = result.get("parameters") or {}
            retry_after = parameters.get("retry_after") if isinstance(parameters, dict) else None
            raise TelegramError(
                f"Telegram rejected the message: {result.get('description', 'unknown error')}",
                status_code=result.get("error_code"),
                retry_after=retry_after if isinstance(retry_after, int) and retry_after > 0 else None,
            )
        sent += 1
    return sent
