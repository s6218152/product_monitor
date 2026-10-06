import pytest

from app.products.price_parser import parse_price


@pytest.mark.parametrize(("text", "expected"), [
    ("22000", 22000), ("22,000", 22000), ("$22000", 22000),
    ("$22,000", 22000), ("NT$22000", 22000), ("NT$22,000", 22000),
    ("售22000", 22000), ("售 22000", 22000), ("售價 22000", 22000),
    ("售價：22000", 22000), ("iPhone 17 Pro Max 512GB 電池98% 42000", 42000),
])
def test_parse_price(text: str, expected: int) -> None:
    assert parse_price(text) == expected


@pytest.mark.parametrize("text", ["256GB", "96%", "2026", "iPhone 17"])
def test_non_prices(text: str) -> None:
    assert parse_price(text) is None
