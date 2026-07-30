"""The manual CSV adapter maps only user-supplied rows and labels them honestly."""

import pytest

from app.domain.discovery import CompanyDiscoveryQuery
from app.services.discovery import ManualCsvCompanyDiscoveryProvider


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
    provider = ManualCsvCompanyDiscoveryProvider(b"name,source_url\nAtlas,record-1\n")
    with pytest.raises(ValueError, match="requires company_name"):
        await provider.search(query())
