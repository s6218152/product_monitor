from __future__ import annotations

import re
from .text import normalize_text


_STORAGE_GB = re.compile(r"(?<!\d)(128|256|512)\s*GB?(?![A-Za-z\d])", re.IGNORECASE)
_STORAGE_TB = re.compile(r"(?<!\d)(1|2)\s*TB(?![A-Za-z\d])", re.IGNORECASE)


def storage_values(text: str) -> set[int]:
    text = normalize_text(text)
    return {int(match.group(1)) for match in _STORAGE_GB.finditer(text)} | {
        int(match.group(1)) * 1024 for match in _STORAGE_TB.finditer(text)
    }


def parse_storage_gb(text: str) -> int | None:
    text = normalize_text(text)
    gb_match = _STORAGE_GB.search(text)
    if gb_match:
        return int(gb_match.group(1))
    tb_match = _STORAGE_TB.search(text)
    return int(tb_match.group(1)) * 1024 if tb_match else None


def format_storage_gb(text: str) -> str:
    storage = parse_storage_gb(text)
    return f"{storage}G" if storage is not None else "容量未提供"
