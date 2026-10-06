from app.products.iphone_parser import parse_iphone


def test_parse_complete_iphone_post() -> None:
    details = parse_iphone("""出售 iPhone 17 Pro Max 256G 黑色
電池健康度 96%
盒裝完整
售 42000
台中面交""")
    assert details.model == "iPhone 17 Pro Max"
    assert details.storage_gb == 256
    assert details.price == 42000
    assert details.color == "黑色"
    assert details.battery_health == 96
    assert details.location == "台中市"
    assert details.transaction == "面交"


def test_parse_pro_max() -> None:
    details = parse_iphone("iPhone17ProMax 512GB 電池98% 45000")
    assert details.model == "iPhone 17 Pro Max"
    assert details.storage_gb == 512
    assert details.battery_health == 98
    assert details.price == 45000


def test_other_iphone_model_is_not_parsed_as_target() -> None:
    assert parse_iphone("iPhone 17 Pro 256GB 售35000").model is None
