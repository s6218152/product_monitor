from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable


def _searchable(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"[\s_-]+", "", normalized)


class KeywordMatcher:
    def __init__(self, keywords: Iterable[str], exclude_keywords: Iterable[str] = ()) -> None:
        self._keywords = tuple(_searchable(word) for word in keywords)
        self._excludes = tuple(_searchable(word) for word in exclude_keywords)
        if not self._keywords:
            raise ValueError("At least one keyword is required")

    def matches(self, text: str) -> bool:
        value = _searchable(text)
        return not any(word in value for word in self._excludes) and any(
            word in value for word in self._keywords
        )
