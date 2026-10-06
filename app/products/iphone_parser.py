from __future__ import annotations

from dataclasses import dataclass
import re

from .price_parser import parse_price
from .location_parser import parse_location


@dataclass(frozen=True, slots=True)
class IPhoneDetails:
    model: str | None
    storage_gb: int | None
    price: int | None
    color: str | None
    battery_health: int | None
    location: str | None
    transaction: str | None


_MODEL = re.compile(r"iphone\s*(17)\s*(pro)\s*(max)", re.IGNORECASE)
_STORAGE = re.compile(r"\b(128|256|512)\s*(?:GB?|G)\b", re.IGNORECASE)
_BATTERY = re.compile(r"(?:電池(?:健康度)?|健康度?)\s*[:：]?\s*(\d{2,3})\s*%", re.IGNORECASE)
_COLORS = ("黑色", "白色", "藍色", "金色", "銀色", "原色", "沙漠色", "鈦金屬")


def parse_iphone(text: str) -> IPhoneDetails:
    model_match = _MODEL.search(text)
    storage_match = _STORAGE.search(text)
    battery_match = _BATTERY.search(text)
    model = None
    if model_match:
        model = f"iPhone {model_match.group(1)} Pro" + (" Max" if model_match.group(3) else "")
    transaction = next((item for item in ("面交", "店到店", "宅配", "寄送") if item in text), None)
    return IPhoneDetails(
        model=model,
        storage_gb=int(storage_match.group(1)) if storage_match else None,
        price=parse_price(text),
        color=next((color for color in _COLORS if color in text), None),
        battery_health=int(battery_match.group(1)) if battery_match else None,
        location=parse_location(text),
        transaction=transaction,
    )
