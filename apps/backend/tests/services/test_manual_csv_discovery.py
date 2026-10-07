"""The manual CSV adapter maps only user-supplied rows and labels them honestly."""

import pytest

from app.domain.discovery import CompanyDiscoveryQuery
from app.services.discovery import ManualCsvCompanyDiscoveryProvider
from app.services.discovery.manual_csv import (
    MAX_MANUAL_CSV_BYTES,
    MAX_MANUAL_CSV_ROWS,
    ManualCsvValidationError,
)


def query(limit: int = 20) -> CompanyDiscoveryQuery:
    return CompanyDiscoveryQuery(
        original_prompt="帮我找 20 家北美五金进口商",
        requested_count=20,
        effective_count=limit,
        region="North America",
        category="hardware",
        keywords=("五金", "hardware", "importer"),
    )


async def test_maps_real_csv_rows_and_preserves_manual_source_label() -> None:
    provider = ManualCsvCompanyDiscoveryProvider(
        b"company_name,source_url,website,region,product_description,import_evidence\n"
        b"Atlas Tools,https://evidence.example/atlas,https://atlas.example,US,"
        b"Hand tools,Shipment record 42\n"
    )
    result = await provider.search(query())
    assert result.failures == ()
    assert len(result.candidates) == 1
    mapped = result.candidates[0]
    assert mapped.source == "manual_csv"
    assert mapped.company_name == "Atlas Tools"
    assert mapped.import_evidence == "Shipment record 42"


async def test_accepts_source_external_id_alias_used_by_calibration_template() -> None:
    provider = ManualCsvCompanyDiscoveryProvider(
        b"company_name,source_external_id,website\n"
        b"Atlas Tools,customer-sample-1,https://atlas.example\n"
    )

    result = await provider.search(query())

    assert len(result.candidates) == 1
    assert result.candidates[0].external_id == "customer-sample-1"


async def test_invalid_row_is_reported_without_aborting_valid_rows() -> None:
    provider = ManualCsvCompanyDiscoveryProvider(
        b"company_name,source_url,external_id\n"
        b"Missing Evidence,,\n"
        b"Valid Importer,https://evidence.example/valid,\n"
    )
    result = await provider.search(query())
    assert [item.company_name for item in result.candidates] == ["Valid Importer"]
    assert len(result.failures) == 1
    assert "row 2" in result.failures[0].reason


async def test_requires_company_name_column() -> None:
    with pytest.raises(ManualCsvValidationError) as caught:
        ManualCsvCompanyDiscoveryProvider(b"name,source_url\nAtlas,record-1\n")
    assert caught.value.error_code == "discovery_csv_invalid_header"


@pytest.mark.parametrize(
    ("content", "error_code"),
    [
        (b"", "discovery_csv_empty"),
        (b"company_name,source_url\n", "discovery_csv_empty"),
        (b"\xff\xfecompany_name,source_url\n", "discovery_csv_invalid_encoding"),
        (b"company_name,website\nAtlas,atlas.example\n", "discovery_csv_invalid_header"),
    ],
)
def test_rejects_file_level_errors_before_search(content: bytes, error_code: str) -> None:
    with pytest.raises(ManualCsvValidationError) as caught:
        ManualCsvCompanyDiscoveryProvider(content)
    assert caught.value.error_code == error_code


def test_rejects_files_above_size_limit() -> None:
    content = b"company_name,source_url\n" + (b"x" * MAX_MANUAL_CSV_BYTES)
    with pytest.raises(ManualCsvValidationError) as caught:
        ManualCsvCompanyDiscoveryProvider(content)
    assert caught.value.error_code == "discovery_csv_too_large"


def test_rejects_files_above_row_limit() -> None:
    rows = ["company_name,source_url"]
    rows.extend(f"Company {index},record-{index}" for index in range(MAX_MANUAL_CSV_ROWS + 1))
    with pytest.raises(ManualCsvValidationError) as caught:
        ManualCsvCompanyDiscoveryProvider("\n".join(rows).encode())
    assert caught.value.error_code == "discovery_csv_too_many_rows"
