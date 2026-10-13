from __future__ import annotations

import re
from .text import normalize_text


_LOCATIONS = {
    "竹北": "新竹縣", "竹東": "新竹縣", "湖口": "新竹縣", "新豐": "新竹縣",
    "芎林": "新竹縣", "關西": "新竹縣", "橫山": "新竹縣", "寶山": "新竹縣",
    "北埔": "新竹縣", "峨眉": "新竹縣", "尖石": "新竹縣", "五峰": "新竹縣",
    "中壢": "桃園市", "平鎮": "桃園市", "八德": "桃園市", "龜山": "桃園市",
    "蘆竹": "桃園市", "大園": "桃園市", "楊梅": "桃園市", "龍潭": "桃園市",
    "大溪": "桃園市", "觀音": "桃園市", "新屋": "桃園市", "復興區": "桃園市",
    "竹南": "苗栗縣", "頭份": "苗栗縣", "後龍": "苗栗縣", "通霄": "苗栗縣",
    "苑裡": "苗栗縣", "公館": "苗栗縣", "銅鑼": "苗栗縣", "三義": "苗栗縣",
    "造橋": "苗栗縣", "頭屋": "苗栗縣", "南庄": "苗栗縣", "三灣": "苗栗縣",
    "獅潭": "苗栗縣", "卓蘭": "苗栗縣", "大湖": "苗栗縣", "泰安": "苗栗縣",
    "台北": "台北市", "臺北": "台北市", "新北": "新北市",
    "桃園市": "桃園市", "桃園縣": "桃園縣", "桃園": "桃園市",
    "新竹市": "新竹市", "新竹縣": "新竹縣", "新竹": "新竹市",
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


def parse_location(text: str, *, source_location: str | None = None) -> str | None:
    text = normalize_text(text)
    candidates = list(_PATTERN.finditer(text))
    choices = []
    for match in candidates:
        before = text[max(0, match.start() - 10):match.start()].rsplit("\n", 1)[-1]
        after = text[match.end():match.end() + 12].split("\n", 1)[0]
        meeting = bool(re.match(r"\s*(?:可)?(?:面交|自取|取貨)", after) or
                       re.search(r"(?:面交|自取|取貨)(?:地點|地區|位置)?\s*[:：]?\s*$", before))
        if not meeting and (re.match(r"\s*(?:101\s*)?(?:購入|購買|買的)", after) or
                            re.search(r"(?:購入|購買)(?:地點|地)?\s*[:：]?\s*$", before)):
            continue
        city = _LOCATIONS[match.group(0)]
        if match.group(0) == "公館" and source_location:
            source = _PATTERN.search(normalize_text(source_location))
            if source:
                city = _LOCATIONS[source.group(0)]
        choices.append((meeting, city))
    return next((city for meeting, city in choices if meeting), choices[0][1] if choices else None)
