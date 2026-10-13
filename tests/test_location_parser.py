import pytest

from app.products.location_parser import parse_location
from app.products.targets import TARGET_LOCATIONS


@pytest.mark.parametrize(("text", "expected"), [
    ("桃園市面交", "桃園市"),
    ("桃園縣自取", "桃園縣"),
    ("苗栗市可面交", "苗栗市"),
    ("苗栗縣寄送", "苗栗縣"),
    ("桃園面交", "桃園市"),
    ("苗栗面交", "苗栗縣"),
])
def test_parse_target_locations(text: str, expected: str) -> None:
    assert parse_location(text) == expected
    assert expected in TARGET_LOCATIONS


@pytest.mark.parametrize(("text", "expected"), [
    ("台北101購入 新竹面交", "新竹市"),
    ("台北購入，面交地點：竹北", "新竹縣"),
    ("購入地點：台北\n面交地點：桃園市", "桃園市"),
    ("新竹面交，台北購入", "新竹市"),
    ("台北購入", None),
])
def test_prefers_transaction_location_over_purchase_city(text: str, expected: str | None) -> None:
    assert parse_location(text) == expected
