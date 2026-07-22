from uuid import uuid4

import pytest

from app.services.import_evidence.upload import EvidenceCsvError, parse_company_csv


@pytest.mark.asyncio
async def test_parse_company_csv_normalizes_and_filters_target() -> None:
    content = (
        b"importer_name,importer_domain,arrival_date,origin_country,house_bol,container_numbers\n"
        b"Target Co,target.example,2026-06-01,CN,HBL-1,MSCU1234567|MSCU1234567\n"
        b"Other Co,other.example,2026-06-02,VN,HBL-2,CMAU1234567\n"
    )

    parsed = await parse_company_csv(
        content,
        company_name="Target Co",
        provider_name="csv",
        request_id=uuid4(),
    )

    assert parsed.records_received == 2
    assert len(parsed.rows) == 1
    assert parsed.rows[0].shipment.container_numbers == ("MSCU1234567",)


@pytest.mark.asyncio
async def test_parse_company_csv_reports_missing_required_column() -> None:
    with pytest.raises(EvidenceCsvError, match="importer_name"):
        await parse_company_csv(
            b"arrival_date,origin_country\n2026-01-01,CN\n",
            company_name="Target Co",
            provider_name="csv",
            request_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_parse_company_csv_rejects_file_over_limit() -> None:
    from app.services.import_evidence.upload import MAX_CSV_BYTES

    with pytest.raises(EvidenceCsvError, match="5MB"):
        await parse_company_csv(
            b"x" * (MAX_CSV_BYTES + 1),
            company_name="Target Co",
            provider_name="csv",
            request_id=uuid4(),
        )
