import pytest

from app.products.target_filter import matches_capacity_price, rejection_reason


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


@pytest.mark.parametrize("text", [
    "iPhone 16 256G 售20000 新竹面交\niPhone 17 Pro Max 256G 售40000",
    "iPhone 17 Pro Max 256G 售30000\n另一支 iPhone 17 Pro Max 256G 售40000",
    "iPhone 17 Pro Max 256G 售30000\niPhone 17 Pro Max 1TB 售50000",
])
def test_rejects_ambiguous_multiple_products(text: str) -> None:
    assert rejection_reason(text, 30000, "新竹市") == "multiple_products"


@pytest.mark.parametrize("text", [
    "【徵】iPhone 17 Pro Max 256G 預算30000 新竹面交",
    "iPhone 17 Pro Max 256G 收購 30000 新竹面交",
    "iPhone 17 Pro Max 256G 手機殼 售5000 新竹面交",
    "iPhone 17 Pro Max 256G 保護殼 售5000 新竹面交",
])
def test_rejects_wanted_or_accessory_subject(text: str) -> None:
    assert rejection_reason(text, 30000, "新竹市") == "wanted_or_accessory"


@pytest.mark.parametrize("text", [
    "iPhone 17 Pro Max 256G 附手機殼 售30000 新竹面交",
    "iPhone 17 Pro Max 256G 贈送一個保護殼 售30000 新竹面交",
    "iPhone 17 Pro Max 256G 附充電線及手機殼 售30000 新竹面交",
    "iPhone 17 Pro Max 256G 手機殼附贈 售30000 新竹面交",
    "iPhone 17 Pro Max 256G 無維修 無更換零件 售30000 新竹面交",
    "iPhone 17 Pro Max 256G 原價45000 售價30000 新竹面交",
    "iPhone 17 Pro Max 256G 售30000 新竹面交\n售價30000",
])
def test_accepts_single_phone_with_gifts_or_repeated_sale_price(text: str) -> None:
    assert rejection_reason(text, 30000, "新竹市") is None


@pytest.mark.parametrize("text", [
    "iPhone 17 Pro Max 256G售30000 新竹面交",
    "iPhone 17 Pro Max ２５６Ｇ 售３００００ 新竹面交",
    "iPhone 17 Pro Max 512GB全新 售37000 新竹面交",
])
def test_accepts_capacity_adjacent_to_chinese_or_fullwidth(text: str) -> None:
    assert rejection_reason(text, 30000, "新竹市") is None
