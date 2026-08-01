"""Small deterministic parser for the D1 natural-language task input."""

import re
from dataclasses import dataclass

DEFAULT_DISCOVERY_COUNT = 20
MAX_DISCOVERY_COUNT = 20

_REGIONS = (
    ("北美", "North America"),
    ("美国", "United States"),
    ("美國", "United States"),
    ("加拿大", "Canada"),
    ("USA", "United States"),
    ("US", "United States"),
)

_CATEGORIES = (
    ("五金", "hardware"),
    ("家具", "furniture"),
    ("健身", "fitness equipment"),
    ("工业", "industrial"),
    ("工業", "industrial"),
    ("照明", "lighting"),
    ("机械", "machinery"),
    ("機械", "machinery"),
)

_CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "兩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


@dataclass(frozen=True)
class ParsedDiscoveryPrompt:
    original_prompt: str
    requested_count: int
    effective_count: int
    region: str
    category: str
    keywords: tuple[str, ...]


def _parse_chinese_number(raw: str) -> int | None:
    if not raw:
        return None
    if raw == "十":
        return 10
    if "百" in raw:
        hundreds, _, rest = raw.partition("百")
        value = _CHINESE_DIGITS.get(hundreds, 1) * 100
        if rest:
            tail = _parse_chinese_number(rest)
            value += tail or 0
        return value
    if "十" in raw:
        tens, _, units = raw.partition("十")
        value = _CHINESE_DIGITS.get(tens, 1) * 10
        value += _CHINESE_DIGITS.get(units, 0)
        return value
    digits = [_CHINESE_DIGITS.get(char) for char in raw]
    if any(value is None for value in digits):
        return None
    return int("".join(str(value) for value in digits))


def _requested_count(prompt: str) -> int:
    arabic = re.search(r"(?<!\d)(\d{1,4})(?!\d)", prompt)
    if arabic:
        return max(1, int(arabic.group(1)))
    chinese = re.search(r"([零〇一二两兩三四五六七八九十百]+)\s*家", prompt)
    if chinese:
        parsed = _parse_chinese_number(chinese.group(1))
        if parsed is not None:
            return max(1, parsed)
    return DEFAULT_DISCOVERY_COUNT


def parse_discovery_prompt(prompt: str) -> ParsedDiscoveryPrompt:
    cleaned = " ".join(prompt.split())
    if not cleaned:
        raise ValueError("prompt must not be empty")

    requested = _requested_count(cleaned)
    region = next((canonical for token, canonical in _REGIONS if token in cleaned), "United States")
    matched_category = next(
        ((token, canonical) for token, canonical in _CATEGORIES if token in cleaned),
        ("进口商", "importer"),
    )
    raw_category, category = matched_category

    keywords: list[str] = [raw_category]
    if category != raw_category:
        keywords.append(category)
    if "进口商" in cleaned and "进口商" not in keywords:
        keywords.append("进口商")
    if "importer" not in keywords:
        keywords.append("importer")

    return ParsedDiscoveryPrompt(
        original_prompt=cleaned,
        requested_count=requested,
        effective_count=min(requested, MAX_DISCOVERY_COUNT),
        region=region,
        category=category,
        keywords=tuple(keywords),
    )
