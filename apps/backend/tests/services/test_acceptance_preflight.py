"""D5e1 synthetic coverage for read-only real-data preflight."""

import io
import zipfile
from typing import BinaryIO, cast

import pytest

from app.services.acceptance import (
    NETEASE_MAPPING_PROFILE,
    AcceptancePreflightError,
    RealDataPreflightService,
)


def _file(content: bytes) -> BinaryIO:
    return cast(BinaryIO, io.BytesIO(content))


def _xlsx(headers: list[str], rows: list[list[str]]) -> bytes:
    shared = headers + [value for row in rows for value in row]
    shared_xml = "".join(f"<si><t>{value}</t></si>" for value in shared)
    indexes = iter(range(len(shared)))
    sheet_rows = []
    for row_number, row in enumerate([headers, *rows], start=1):
        cells = []
        for column, _value in enumerate(row):
            index = next(indexes)
            letter = chr(ord("A") + column)
            cells.append(f'<c r="{letter}{row_number}" t="s"><v>{index}</v></c>')
        sheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
            <sheets><sheet name="客户与贸易" sheetId="1" r:id="rId1"/></sheets></workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
            <Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/>
            </Relationships>""",
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{shared_xml}</sst>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
            f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>",
        )
    return output.getvalue()


def test_netease_csv_preflight_infers_mixed_mapping_and_quality_counts() -> None:
    content = (
        "公司名称,客户ID,官网,联系人,邮箱,产品,HS编码,进口日期,未知列\n"
        "Atlas Tools,A-1,https://atlas.example,Ada,ada@atlas.example,hinges,8302,2026-07-01,x\n"
        "Atlas Tools,A-1,https://atlas.example,Ben,info@atlas.example,locks,8301,2026-07-02,y\n"
        ",,,,,,,,\n"
    ).encode()

    report = RealDataPreflightService().preflight_netease(
        _file(content), filename="netease.csv"
    )

    assert report.mapping_profile == NETEASE_MAPPING_PROFILE
    assert report.inferred_data_type == "mixed"
    assert report.suggested_mapping["company_name"] == "公司名称"
    assert report.suggested_mapping["contact_email"] == "邮箱"
    assert report.suggested_mapping["product_description"] == "产品"
    assert report.source_columns[0] == "公司名称"
    assert report.sample_values["company_name"] == "A••••••s"
    assert report.sample_values["contact_email"] == "a•a@a•••s.example"
    assert "ada@atlas.example" not in repr(report.sample_values)
    assert report.unknown_fields == ("未知列",)
    assert report.empty_rows == 1
    assert report.estimated_company_count == 1
    assert report.estimated_contact_count == 2
    assert report.estimated_trade_record_count == 2
    assert report.estimated_high_confidence_reviews == 1
    assert report.coverage["external_company_id"] == 1.0
    assert report.no_business_side_effects is True


def test_netease_xlsx_preflight_and_manual_mapping_override() -> None:
    content = _xlsx(
        ["企业", "邮件地址", "货品", "日期字段"],
        [["Pacific Hardware", "buyer@pacific.example", "fasteners", "2026-07-01"]],
    )

    report = RealDataPreflightService().preflight_netease(
        _file(content),
        filename="netease.xlsx",
        mapping={
            "company_name": "企业",
            "contact_email": "邮件地址",
            "product_description": "货品",
            "shipment_date": "日期字段",
        },
    )

    assert report.file_type == "xlsx"
    assert report.encoding == "xlsx-xml"
    assert report.sheets == ("客户与贸易",)
    assert report.total_rows == 1
    assert report.manual_mapping_applied is True
    assert set(report.mapping_confidence.values()) == {"manual"}
    assert report.inferred_data_type == "mixed"


def test_netease_gb18030_aliases_and_invalid_encoding() -> None:
    valid = "公司,电子邮箱\n宁波五金,buyer@example.test\n".encode("gb18030")
    report = RealDataPreflightService().preflight_netease(
        _file(valid), filename="netease.csv"
    )
    assert report.encoding == "gb18030"
    assert report.suggested_mapping["company_name"] == "公司"
    assert report.suggested_mapping["contact_email"] == "电子邮箱"

    with pytest.raises(AcceptancePreflightError) as caught:
        RealDataPreflightService().preflight_netease(
            _file(b"\xff\xff\xff"), filename="invalid.csv"
        )
    assert caught.value.code == "acceptance_invalid_encoding"


def test_empty_file_and_invalid_manual_mapping_are_rejected() -> None:
    service = RealDataPreflightService()
    with pytest.raises(AcceptancePreflightError) as empty:
        service.preflight_netease(_file(b""), filename="empty.csv")
    assert empty.value.code == "acceptance_file_empty"

    with pytest.raises(AcceptancePreflightError) as mapping:
        service.preflight_netease(
            _file(b"company\nAtlas\n"),
            filename="data.csv",
            mapping={"company_name": "missing"},
        )
    assert mapping.value.code == "acceptance_mapping_invalid"


def test_umail_preflight_reports_distribution_coverage_and_match_estimates() -> None:
    content = (
        "导出行ID,导出批次ID,邮箱,任务名称,状态,发生时间,退信类型\n"
        "5d94fdf4-865c-4fdb-866b-6d45ec733ee5,batch-1,a@example.test,c1,delivered,2026-08-01T10:00:00Z,\n"
        ",batch-1,b@example.test,c1,hard_bounce,2026/08/01 11:00:00,hard\n"
        ",batch-1,b@example.test,c1,unknown_event,,\n"
    ).encode()

    report = RealDataPreflightService().preflight_umail(
        _file(content), filename="umail.csv"
    )

    assert report.suggested_mapping["export_row_id"] == "导出行ID"
    assert report.suggested_mapping["event_type"] == "状态"
    assert report.event_type_distribution == {
        "delivered": 1,
        "hard_bounced": 1,
        "unsupported": 1,
    }
    assert report.time_format_distribution == {
        "iso8601": 1,
        "missing": 1,
        "yyyy/mm/dd_hms": 1,
    }
    assert report.bounce_type_distribution == {"hard": 1}
    assert report.estimated_strong_id_matches == 1
    assert report.estimated_email_fallback_matches == 2
    assert report.estimated_ambiguous_rows == 2
    assert report.unsupported_event_count == 1
    assert report.missing_occurred_at_count == 1
    assert report.coverage["email"] == 1.0
    assert report.no_business_side_effects is True
