import pytest

from app.products.matcher import KeywordMatcher


@pytest.mark.parametrize("text", [
    "iPhone 17 Pro Max 台灣公司貨 售42000",
    "iPhone17 Pro Max 全新未拆 43500",
    "iPhone17ProMax 二手 39000",
    "iphone-17-pro-max 現貨",
])
def test_iphone_17_pro_max_matches(text: str) -> None:
    matcher = KeywordMatcher(("iPhone 17 Pro Max",), ("徵", "保護殼"))
    assert matcher.matches(text)


@pytest.mark.parametrize("text", ["徵 iPhone 17 Pro Max", "iPhone 17 Pro Max 保護殼 500", "iPhone 17 Pro"])
def test_iphone_17_pro_max_exclusions(text: str) -> None:
    matcher = KeywordMatcher(("iPhone 17 Pro Max",), ("徵", "保護殼"))
    assert not matcher.matches(text)
