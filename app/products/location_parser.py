from __future__ import annotations

import re


_LOCATIONS = {
    "台北": "台北市", "臺北": "台北市", "新北": "新北市",
    "桃園市": "桃園市", "桃園縣": "桃園縣", "桃園": "桃園市",
    "新竹市": "新竹市", "新竹縣": "新竹縣", "新竹": "新竹",
    "苗栗市": "苗栗市", "苗栗縣": "苗栗縣", "苗栗": "苗栗縣",
    "台中": "台中市", "臺中": "台中市",
    "彰化": "彰化縣", "南投": "南投縣", "雲林": "雲林縣",
    "嘉義市": "嘉義市", "嘉義縣": "嘉義縣", "嘉義": "嘉義",
    "台南": "台南市", "臺南": "台南市", "高雄": "高雄市",
    "屏東": "屏東縣", "宜蘭": "宜蘭縣", "花蓮": "花蓮縣",
    "台東": "台東縣", "臺東": "台東縣", "基隆": "基隆市",
    "澎湖": "澎湖縣", "金門": "金門縣", "連江": "連江縣",
}
_PATTERN = re.compile("|".join(sorted(map(re.escape, _LOCATIONS), key=len, reverse=True)))


def parse_location(text: str) -> str | None:
    match = _PATTERN.search(text)
    return _LOCATIONS[match.group(0)] if match else None
