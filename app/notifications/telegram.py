from __future__ import annotations

from datetime import datetime
from html import escape
from sqlite3 import Row
from zoneinfo import ZoneInfo
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.products.storage_parser import format_storage_gb


TAIPEI = ZoneInfo("Asia/Taipei")


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
                f"📱 容量：<b>{_format_storage(listing['title'], listing['description'])}</b>",
                f"💰 {price}",
                f"📍 地區：{escape(listing['location'] or '未提供')}",
                f"🕒 上架：{_format_time(listing['last_seen_at'])}",
                f'🔗 商品連結：<a href="{url}">{url}</a>',
            ))
        )
    return "\n\n".join(blocks)


def _split_message(message: str, limit: int = 4000) -> list[str]:
    parts: list[str] = []
    current = ""
    for block in message.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                parts.append(current)
            current = block
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
            detail = json.loads(error.read().decode("utf-8")).get("description", "HTTP error")
            raise RuntimeError(f"Telegram rejected the message: {detail}") from error
        except URLError as error:
            raise RuntimeError(f"Could not reach Telegram: {error.reason}") from error
        if not result.get("ok"):
            raise RuntimeError(f"Telegram rejected the message: {result.get('description', 'unknown error')}")
        sent += 1
    return sent
