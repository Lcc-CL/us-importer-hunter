"""Unified CSV/XLSX tabular intake: parsing, inheritance, summary semantics."""

import io
import tempfile
import zipfile
from typing import Any, BinaryIO, cast
from uuid import uuid4

from app.domain.bulk_import import RawImportRowStatus
from app.services.acceptance import RealDataPreflightService
from app.services.bulk_import import BulkTabularIntake

_XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _cell(column: str, row: int, value: str) -> str:
    escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f'<c r="{column}{row}" t="inlineStr"><is><t>{escaped}</t></is></c>'
    )


def _build_xlsx(
    *,
    sheet_name: str,
    headers: list[str],
    rows: list[list[str]],
    merges: list[str] | None = None,
) -> bytes:
    columns = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    sheet_rows: list[str] = []
    sheet_rows.append(
        "<row r=\"1\">"
        + "".join(_cell(columns[i], 1, header) for i, header in enumerate(headers))
        + "</row>"
    )
    for row_index, values in enumerate(rows, start=2):
        sheet_rows.append(
            f'<row r="{row_index}">'
            + "".join(
                _cell(columns[i], row_index, value)
                for i, value in enumerate(values)
                if value
            )
            + "</row>"
        )
    merge_xml = ""
    if merges:
        merge_xml = "<mergeCells count=\"{}\">{}</mergeCells>".format(
            len(merges),
            "".join(f'<mergeCell ref="{ref}"/>' for ref in merges),
        )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<worksheet xmlns="{_XLSX_NS}"><sheetData>'
        + "".join(sheet_rows)
        + f"</sheetData>{merge_xml}</worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<workbook xmlns="{_XLSX_NS}" xmlns:r="{_REL_NS}">'
        '<sheets><sheet name="{0}" sheetId="1" r:id="rId1"/></sheets></workbook>'.format(
            sheet_name
        )
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        archive.writestr("[Content_Types].xml", "<?xml version=\"1.0\"?><Types/>")
    return buffer.getvalue()


def binary_file(content: bytes) -> BinaryIO:
    file = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    file.write(content)
    file.seek(0)
    return cast(BinaryIO, file)


def _intake_rows(content: bytes, mapping: dict[str, str]) -> list[Any]:
    intake = BulkTabularIntake()
    with binary_file(content) as file:
        preflight = intake.preflight(
            file,
            mapping=mapping,
            filename="synthetic.xlsx",
        )
        batches = intake.iter_batches(
            file,
            session_id=uuid4(),
            preflight=preflight,
            mapping=mapping,
        )
        return [row for batch in batches for row in batch]


def test_xlsx_preflight_and_rows_are_unified() -> None:
    content = _build_xlsx(
        sheet_name="客户线索",
        headers=["公司名称", "联系人姓名"],
        rows=[["A公司", "王五"], ["B公司", "赵六"]],
    )

    with binary_file(content) as file:
        intake = BulkTabularIntake()
        preflight = intake.preflight(
            file,
            mapping={"company_name": "公司名称", "contact_name": "联系人姓名"},
            filename="synthetic.xlsx",
        )
        assert preflight.file_type == "xlsx"
        assert preflight.sheet_name == "客户线索"
        assert preflight.headers == ("公司名称", "联系人姓名")
        assert preflight.total_rows == 2
        batches = intake.iter_batches(
            file,
            session_id=uuid4(),
            preflight=preflight,
            mapping={"company_name": "公司名称", "contact_name": "联系人姓名"},
        )
        rows = [row for batch in batches for row in batch]

    assert [row.row_number for row in rows] == [2, 3]
    assert rows[0].raw_payload["fields"]["公司名称"] == "A公司"
    assert rows[0].raw_payload["sheet"] == "客户线索"


def test_merged_cell_contact_inheritance_links_contact_to_company() -> None:
    content = _build_xlsx(
        sheet_name="客户线索",
        headers=["公司名称", "官网", "联系人姓名"],
        rows=[
            ["A公司", "acme.example", "王五"],
            ["", "", "赵六"],
        ],
        merges=["A2:A3", "B2:B3"],
    )
    rows = _intake_rows(
        content,
        mapping={
            "company_name": "公司名称",
            "website": "官网",
            "contact_name": "联系人姓名",
        },
    )

    assert len(rows) == 2
    assert rows[0].raw_payload["company_anchor_row"] == 2
    inherited = rows[1].raw_payload
    assert inherited["fields"]["公司名称"] == "A公司"
    assert inherited["fields"]["官网"] == "acme.example"
    assert inherited["inherited_company_source_row"] == 2
    assert inherited["grouping_rule"] == "xlsx_vertical_merge"
    assert inherited["grouping_confidence"] == "high"
    assert set(inherited["inherited_fields"]) == {"公司名称", "官网"}
    assert rows[1].status is RawImportRowStatus.ACCEPTED


def test_orphan_contact_is_not_forward_filled_without_merge_evidence() -> None:
    content = _build_xlsx(
        sheet_name="客户线索",
        headers=["公司名称", "联系人姓名"],
        rows=[["A公司", "王五"], ["", "赵六"]],
        merges=[],
    )
    rows = _intake_rows(
        content,
        mapping={"company_name": "公司名称", "contact_name": "联系人姓名"},
    )

    orphan = rows[1].raw_payload
    assert orphan["fields"]["公司名称"] == ""
    assert orphan["grouping_rule"] == "none"
    assert orphan["grouping_confidence"] == "low"
    assert orphan["company_review_required"] is True


def test_duplicate_rows_are_classified_without_losing_originals() -> None:
    content = _build_xlsx(
        sheet_name="CSV",
        headers=["公司名称", "联系人邮箱"],
        rows=[["A公司", "a@example.com"], ["A公司", "a@example.com"]],
    )
    rows = _intake_rows(
        content,
        mapping={"company_name": "公司名称", "contact_email": "联系人邮箱"},
    )

    assert [row.status for row in rows] == [
        RawImportRowStatus.ACCEPTED,
        RawImportRowStatus.DUPLICATE,
    ]


def test_company_import_summary_annotation_and_unknown_currency() -> None:
    content = _build_xlsx(
        sheet_name="客户线索",
        headers=["公司名称", "HS code", "进口金额"],
        rows=[["A公司", "8205", "$118,000"], ["B公司", "9401", "¥50,000"]],
    )
    rows = _intake_rows(
        content,
        mapping={
            "company_name": "公司名称",
            "hs_code": "HS code",
            "amount": "进口金额",
        },
    )

    first = rows[0].raw_payload
    assert first["record_kind"] == "company_import_summary"
    assert first["import_value_raw"] == "$118,000"
    assert first["currency"] == "unknown"
    assert rows[1].raw_payload["currency"] == "cny"


def test_ticket_fields_suppress_company_summary_tag() -> None:
    content = _build_xlsx(
        sheet_name="shipments",
        headers=["公司名称", "HS code", "进口日期", "数量"],
        rows=[["A公司", "8205", "2026-07-01", "10"]],
    )
    rows = _intake_rows(
        content,
        mapping={
            "company_name": "公司名称",
            "hs_code": "HS code",
            "shipment_date": "进口日期",
            "quantity": "数量",
        },
    )

    assert "record_kind" not in rows[0].raw_payload


def test_mapping_aliases_and_confidence_for_netease_headers() -> None:
    content = _build_xlsx(
        sheet_name="客户线索",
        headers=[
            "公司名称",
            "官网",
            "联系人姓名",
            "联系人职位",
            "联系人邮箱",
            "HS code",
            "最大供应商",
            "进口金额",
            "国家/地区",
        ],
        rows=[
            [
                "A公司",
                "acme.example",
                "王五",
                "经理",
                "a@example.com",
                "8205",
                "S1",
                "$1",
                "美国",
            ]
        ],
    )
    service = RealDataPreflightService()
    with binary_file(content) as file:
        report = service.preflight_netease(
            file,
            filename="synthetic.xlsx",
            mapping=None,
        )

    suggested = report.suggested_mapping
    confidence = report.mapping_confidence
    assert suggested["contact_email"] == "联系人邮箱"
    assert confidence["contact_email"] == "high"
    assert suggested["contact_title"] == "联系人职位"
    assert confidence["contact_title"] == "high"
    assert suggested["hs_code"] == "HS code"
    assert confidence["hs_code"] == "high"
    assert suggested["company_name"] == "公司名称"
    assert confidence["company_name"] == "high"
    assert suggested["supplier"] == "最大供应商"
    assert confidence["supplier"] == "high"
    assert suggested["amount"] == "进口金额"
    assert confidence["amount"] == "medium"
    assert suggested["country"] == "国家/地区"
    assert confidence["country"] == "medium"
