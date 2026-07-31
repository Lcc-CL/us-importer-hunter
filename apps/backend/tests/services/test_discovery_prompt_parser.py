"""Deterministic parsing for the D1 one-sentence discovery command."""

import pytest

from app.services.discovery import MAX_DISCOVERY_COUNT, parse_discovery_prompt


@pytest.mark.parametrize(
    ("prompt", "requested"),
    [
        ("帮我找 20 家北美五金进口商", 20),
        ("帮我找二十家美国健身器材进口商", 20),
        ("找 100 家美国照明设备进口商", 100),
        ("寻找十二家加拿大照明进口商", 12),
    ],
)
def test_parses_arabic_and_chinese_counts(prompt: str, requested: int) -> None:
    parsed = parse_discovery_prompt(prompt)
    assert parsed.requested_count == requested
    assert parsed.effective_count == min(requested, MAX_DISCOVERY_COUNT)


def test_extracts_region_category_and_keywords() -> None:
    parsed = parse_discovery_prompt("帮我找 20 家北美五金进口商")
    assert parsed.region == "North America"
    assert parsed.category == "hardware"
    assert parsed.keywords == ("五金", "hardware", "进口商", "importer")


def test_defaults_count_and_us_region() -> None:
    parsed = parse_discovery_prompt("帮我找美国进口商")
    assert parsed.requested_count == 20
    assert parsed.effective_count == 20
    assert parsed.region == "United States"
    assert parsed.category == "importer"


def test_plain_text_uses_understandable_mvp_defaults_without_llm() -> None:
    parsed = parse_discovery_prompt("一段无法识别行业的普通文本")
    assert parsed.original_prompt == "一段无法识别行业的普通文本"
    assert parsed.requested_count == 20
    assert parsed.effective_count == 20
    assert parsed.region == "United States"
    assert parsed.category == "importer"


def test_preserves_requested_count_above_mvp_limit() -> None:
    parsed = parse_discovery_prompt("帮我找 100 家北美五金进口商")
    assert parsed.requested_count == 100
    assert parsed.effective_count == 20


def test_rejects_blank_prompt() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        parse_discovery_prompt("   ")
