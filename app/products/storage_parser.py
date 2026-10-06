from __future__ import annotations

import re


_STORAGE_GB = re.compile(r"(?<!\d)(128|256|512)\s*(?:GB?|G)\b", re.IGNORECASE)
_STORAGE_TB = re.compile(r"(?<!\d)(1|2)\s*TB\b", re.IGNORECASE)


def parse_storage_gb(text: str) -> int | None:
    gb_match = _STORAGE_GB.search(text)
    if gb_match:
        return int(gb_match.group(1))
    tb_match = _STORAGE_TB.search(text)
    return int(tb_match.group(1)) * 1024 if tb_match else None


def format_storage_gb(text: str) -> str:
    storage = parse_storage_gb(text)
    return f"{storage}G" if storage is not None else "容量未提供"
