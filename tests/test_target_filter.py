import pytest

from app.products.target_filter import matches_capacity_price


@pytest.mark.parametrize(("text", "price"), [
    ("iPhone 17 Pro Max 512G", 37000),
    ("容量：512GB", 36000),
    ("iPhone 17 Pro Max 256G", 32000),
    ("容量：256GB", 31000),
])
def test_matches_capacity_price(text: str, price: int) -> None:
    assert matches_capacity_price(text, price)


@pytest.mark.parametrize(("text", "price"), [
    ("iPhone 17 Pro Max 512G", 37001),
    ("iPhone 17 Pro Max 256G", 32001),
    ("iPhone 17 Pro Max 1TB", 32000),
    ("iPhone 17 Pro Max", 30000),
    ("iPhone 17 Pro Max 256G", None),
])
def test_rejects_non_matching_capacity_price(text: str, price: int | None) -> None:
    assert not matches_capacity_price(text, price)
