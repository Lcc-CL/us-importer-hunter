"""Bounded, read-only preflight for real NetEase and Umail files.

The service deliberately returns aggregate metadata only. It never persists
uploaded bytes, emits row payloads, calls providers, or creates business data.
"""

from __future__ import annotations

import codecs
import csv
import hashlib
import io
import re
import zipfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Literal
from uuid import UUID
from xml.etree import ElementTree

ACCEPTANCE_MAX_BYTES = 20 * 1024 * 1024
ACCEPTANCE_MAX_ROWS = 20_000
XLSX_MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
NETEASE_MAPPING_PROFILE = "netease-foreign-trade-v1"
UMAIL_MAPPING_PROFILE = "umail-result-preflight-v1"

_HEADER_NORMALIZER = re.compile(r"[^a-z0-9\u4e00-\u9fff]+")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CELL_REFERENCE = re.compile(r"([A-Z]+)")

NETEASE_ALIASES: dict[str, tuple[str, ...]] = {
    "company_name": (
        "company_name",
        "company",
        "customer",
        "importer",
        "consignee",
        "公司名称",
        "公司",
        "客户名称",
        "企业名称",
        "进口商",
        "收货人",
    ),
    "external_company_id": (
        "external_company_id",
        "external_id",
        "company_id",
        "customer_id",
        "客户id",
        "企业id",
        "公司id",
    ),
    "website": ("website", "domain", "url", "官网", "网站", "公司网站", "域名"),
    "address": ("address", "company_address", "公司地址", "地址", "注册地址"),
    "country": ("country", "company_country", "国家", "公司国家", "地区"),
    "company_type": ("company_type", "公司类型", "企业类型", "客户类型"),
    "phone": ("phone", "company_phone", "公司电话", "总机"),
    "contact_name": ("contact_name", "contact", "联系人", "联系人姓名", "姓名"),
    "contact_title": ("contact_title", "title", "job_title", "职位", "职务", "岗位"),
    "contact_email": ("contact_email", "email", "邮箱", "电子邮箱", "邮件地址"),
    "contact_phone": (
        "contact_phone",
        "mobile",
        "mobile_phone",
        "联系人电话",
        "手机",
        "手机号",
    ),
    "contact_linkedin": ("contact_linkedin", "linkedin", "linkedin_url"),
    "hs_code": ("hs_code", "hscode", "hs code", "海关编码", "hs编码", "商品编码"),
    "product_description": (
        "product_description",
        "product",
        "commodity",
        "goods_description",
        "产品",
        "产品描述",
        "商品描述",
        "品名",
    ),
    "origin_country": (
        "origin_country",
        "country_of_origin",
        "supplier_country",
        "来源国",
        "原产国",
        "供应商国家",
    ),
    "shipment_date": (
        "shipment_date",
        "arrival_date",
        "import_date",
        "date",
        "进口日期",
        "到港日期",
        "提单日期",
    ),
    "quantity": ("quantity", "qty", "数量", "件数"),
    "weight": ("weight", "weight_kg", "gross_weight", "重量", "毛重"),
    "amount": ("amount", "value", "trade_value", "金额", "货值", "总价"),
    "pol": ("pol", "port_of_loading", "loading_port", "起运港", "装货港"),
    "pod": (
        "pod",
        "port_of_discharge",
        "destination_port",
        "目的港",
        "卸货港",
    ),
}

UMAIL_ALIASES: dict[str, tuple[str, ...]] = {
    "export_batch_id": ("export_batch_id", "batch_id", "导出批次id", "批次id"),
    "export_row_id": ("export_row_id", "row_id", "导出行id", "行id"),
    "email": ("email", "recipient", "recipient_email", "收件人", "邮箱"),
    "campaign": ("campaign", "campaign_name", "活动", "任务名称", "邮件任务"),
    "event_type": ("event_type", "event", "status", "事件", "状态", "发送状态"),
    "occurred_at": (
        "occurred_at",
        "event_time",
        "timestamp",
        "time",
        "发生时间",
        "事件时间",
        "时间",
    ),
    "bounce_type": ("bounce_type", "bounce", "退信类型", "退信原因"),
    "message_id": ("message_id", "mail_id", "邮件id", "消息id"),
}

_COMPANY_FIELDS = frozenset(
    {"company_name", "external_company_id", "website", "address", "country", "company_type"}
)
_CONTACT_FIELDS = frozenset(
    {"contact_name", "contact_title", "contact_email", "contact_phone", "contact_linkedin"}
)
_TRADE_FIELDS = frozenset(
    {
        "hs_code",
        "product_description",
        "origin_country",
        "shipment_date",
        "quantity",
        "weight",
        "amount",
        "pol",
        "pod",
    }
)

_EVENT_ALIASES = {
    "sent": "sent",
    "send": "sent",
    "delivered": "delivered",
    "delivery": "delivered",
    "hard_bounce": "hard_bounced",
    "hard_bounced": "hard_bounced",
    "soft_bounce": "soft_bounced",
    "soft_bounced": "soft_bounced",
    "bounce_unknown": "bounce_unknown",
    "unknown_bounce": "bounce_unknown",
    "unsubscribed": "unsubscribed",
    "unsubscribe": "unsubscribed",
    "opt_out": "unsubscribed",
    "complained": "complained",
    "complaint": "complained",
    "spam_complaint": "complained",
    "replied": "replied",
    "reply": "replied",
    "opened": "opened",
    "open": "opened",
    "clicked": "clicked",
    "click": "clicked",
}


class AcceptancePreflightError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class _Sheet:
    name: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class _TabularFile:
    file_type: Literal["csv", "xlsx"]
    file_size_bytes: int
    file_sha256: str
    encoding: str
    sheets: tuple[_Sheet, ...]


@dataclass(frozen=True)
class NetEasePreflightReport:
    file_type: Literal["csv", "xlsx"]
    file_size_bytes: int
    file_sha256: str
    encoding: str
    sheets: tuple[str, ...]
    selected_sheet: str
    total_rows: int
    analyzed_rows: int
    inferred_data_type: Literal["company", "contact", "shipment", "mixed", "unknown"]
    mapping_profile: str
    suggested_mapping: dict[str, str]
    mapping_confidence: dict[str, str]
    source_columns: tuple[str, ...]
    sample_values: dict[str, str]
    manual_mapping_applied: bool
    unknown_fields: tuple[str, ...]
    missing_required_fields: tuple[str, ...]
    duplicate_columns: tuple[str, ...]
    empty_rows: int
    invalid_rows: int
    estimated_company_count: int
    estimated_contact_count: int
    estimated_trade_record_count: int
    coverage: dict[str, float]
    estimated_high_confidence_reviews: int
    estimated_medium_confidence_reviews: int
    no_business_side_effects: bool = True


@dataclass(frozen=True)
class UmailPreflightReport:
    file_type: Literal["csv"]
    file_size_bytes: int
    file_sha256: str
    encoding: str
    total_rows: int
    mapping_profile: str
    suggested_mapping: dict[str, str]
    mapping_confidence: dict[str, str]
    source_columns: tuple[str, ...]
    sample_values: dict[str, str]
    manual_mapping_applied: bool
    unknown_fields: tuple[str, ...]
    missing_required_fields: tuple[str, ...]
    duplicate_columns: tuple[str, ...]
    event_type_distribution: dict[str, int]
    time_format_distribution: dict[str, int]
    bounce_type_distribution: dict[str, int]
    coverage: dict[str, float]
    estimated_strong_id_matches: int
    estimated_email_fallback_matches: int
    estimated_ambiguous_rows: int
    unsupported_event_count: int
    missing_occurred_at_count: int
    invalid_rows: int
    match_estimate_basis: Literal["file_identifiers_only", "database_snapshot"]
    no_business_side_effects: bool = True


class RealDataPreflightService:
    """Inspects bounded files without crossing into persistence or providers."""

    def preflight_netease(
        self,
        file: BinaryIO,
        *,
        filename: str,
        mapping: Mapping[str, str] | None = None,
    ) -> NetEasePreflightReport:
        tabular = _read_tabular(file, filename=filename, allow_xlsx=True)
        sheet = _select_sheet(tabular.sheets, NETEASE_ALIASES)
        suggested, confidence = _infer_mapping(
            sheet.headers,
            aliases=NETEASE_ALIASES,
            manual_mapping=mapping or {},
        )
        duplicate_columns = _duplicates(sheet.headers)
        total_rows = sum(len(candidate.rows) for candidate in tabular.sheets)
        analysis = _analyze_netease_rows(sheet, suggested)
        mapped_columns = set(suggested.values())
        missing_required = () if "company_name" in suggested else ("company_name",)
        return NetEasePreflightReport(
            file_type=tabular.file_type,
            file_size_bytes=tabular.file_size_bytes,
            file_sha256=tabular.file_sha256,
            encoding=tabular.encoding,
            sheets=tuple(candidate.name for candidate in tabular.sheets),
            selected_sheet=sheet.name,
            total_rows=total_rows,
            analyzed_rows=len(sheet.rows),
            inferred_data_type=analysis.inferred_data_type,
            mapping_profile=NETEASE_MAPPING_PROFILE,
            suggested_mapping=suggested,
            mapping_confidence=confidence,
            source_columns=sheet.headers,
            sample_values=_masked_samples(sheet, suggested),
            manual_mapping_applied=bool(mapping),
            unknown_fields=tuple(
                header for header in sheet.headers if header not in mapped_columns
            ),
            missing_required_fields=missing_required,
            duplicate_columns=duplicate_columns,
            empty_rows=analysis.empty_rows,
            invalid_rows=analysis.invalid_rows,
            estimated_company_count=analysis.company_count,
            estimated_contact_count=analysis.contact_count,
            estimated_trade_record_count=analysis.trade_record_count,
            coverage=analysis.coverage,
            estimated_high_confidence_reviews=analysis.high_confidence,
            estimated_medium_confidence_reviews=analysis.medium_confidence,
        )

    def preflight_umail(
        self,
        file: BinaryIO,
        *,
        filename: str,
        mapping: Mapping[str, str] | None = None,
    ) -> UmailPreflightReport:
        tabular = _read_tabular(file, filename=filename, allow_xlsx=False)
        sheet = tabular.sheets[0]
        suggested, confidence = _infer_mapping(
            sheet.headers,
            aliases=UMAIL_ALIASES,
            manual_mapping=mapping or {},
        )
        duplicate_columns = _duplicates(sheet.headers)
        mapped_columns = set(suggested.values())
        rows = _row_dicts(sheet)
        event_counts: Counter[str] = Counter()
        time_formats: Counter[str] = Counter()
        bounce_counts: Counter[str] = Counter()
        unsupported = 0
        missing_time = 0
        invalid_rows = 0
        strong_ids = 0
        email_fallback = 0
        match_keys: list[str] = []
        for row in rows:
            row_invalid = False
            event_value = _mapped_value(row, suggested, "event_type")
            event = _normalize_event(event_value)
            if event is None:
                if event_value:
                    event_counts["unsupported"] += 1
                    unsupported += 1
                else:
                    event_counts["missing"] += 1
                    row_invalid = True
            else:
                event_counts[event] += 1
            occurred_at = _mapped_value(row, suggested, "occurred_at")
            time_format = _time_format(occurred_at)
            time_formats[time_format] += 1
            if not occurred_at:
                missing_time += 1
                row_invalid = True
            elif time_format == "unrecognized":
                row_invalid = True
            bounce_value = _mapped_value(row, suggested, "bounce_type")
            if bounce_value:
                bounce_counts[_normalized_token(bounce_value)] += 1
            row_id = _mapped_value(row, suggested, "export_row_id")
            email = _mapped_value(row, suggested, "email").casefold()
            campaign = _mapped_value(row, suggested, "campaign").casefold()
            if _valid_uuid(row_id):
                strong_ids += 1
                match_keys.append(f"id:{row_id.casefold()}")
            elif _valid_email(email):
                email_fallback += 1
                match_keys.append(f"email:{campaign}:{email}")
            else:
                match_keys.append("")
            if row_invalid:
                invalid_rows += 1
        key_counts = Counter(key for key in match_keys if key)
        ambiguous = sum(1 for key in match_keys if key and key_counts[key] > 1)
        denominator = max(1, len(rows))
        coverage = {
            logical: round(
                sum(bool(_mapped_value(row, suggested, logical)) for row in rows)
                / denominator,
                4,
            )
            for logical in ("export_row_id", "export_batch_id", "email", "campaign")
        }
        missing_required = tuple(
            field for field in ("event_type", "occurred_at") if field not in suggested
        )
        return UmailPreflightReport(
            file_type="csv",
            file_size_bytes=tabular.file_size_bytes,
            file_sha256=tabular.file_sha256,
            encoding=tabular.encoding,
            total_rows=len(rows),
            mapping_profile=UMAIL_MAPPING_PROFILE,
            suggested_mapping=suggested,
            mapping_confidence=confidence,
            source_columns=sheet.headers,
            sample_values=_masked_samples(sheet, suggested),
            manual_mapping_applied=bool(mapping),
            unknown_fields=tuple(
                header for header in sheet.headers if header not in mapped_columns
            ),
            missing_required_fields=missing_required,
            duplicate_columns=duplicate_columns,
            event_type_distribution=dict(sorted(event_counts.items())),
            time_format_distribution=dict(sorted(time_formats.items())),
            bounce_type_distribution=dict(sorted(bounce_counts.items())),
            coverage=coverage,
            estimated_strong_id_matches=strong_ids,
            estimated_email_fallback_matches=email_fallback,
            estimated_ambiguous_rows=ambiguous,
            unsupported_event_count=unsupported,
            missing_occurred_at_count=missing_time,
            invalid_rows=invalid_rows,
            match_estimate_basis="file_identifiers_only",
        )


@dataclass(frozen=True)
class _NetEaseAnalysis:
    inferred_data_type: Literal["company", "contact", "shipment", "mixed", "unknown"]
    empty_rows: int
    invalid_rows: int
    company_count: int
    contact_count: int
    trade_record_count: int
    coverage: dict[str, float]
    high_confidence: int
    medium_confidence: int


def _analyze_netease_rows(
    sheet: _Sheet,
    mapping: Mapping[str, str],
) -> _NetEaseAnalysis:
    rows = _row_dicts(sheet)
    company_keys: set[str] = set()
    contact_keys: set[str] = set()
    empty_rows = 0
    invalid_rows = 0
    trade_records = 0
    high_keys: set[str] = set()
    medium_keys: set[str] = set()
    has_company = False
    has_contact = False
    has_trade = False
    for position, (source_row, row) in enumerate(zip(sheet.rows, rows, strict=True), start=1):
        values = tuple(value.strip() for value in row.values())
        if not any(values):
            empty_rows += 1
            invalid_rows += 1
            continue
        if len(source_row) != len(sheet.headers):
            invalid_rows += 1
        company_name = _mapped_value(row, mapping, "company_name")
        external_id = _mapped_value(row, mapping, "external_company_id")
        website = _mapped_value(row, mapping, "website")
        address = _mapped_value(row, mapping, "address")
        company_key = (
            f"external:{external_id.casefold()}"
            if external_id
            else f"website:{_domain(website)}"
            if _domain(website)
            else f"name:{_normalized_token(company_name)}"
            if company_name
            else f"row:{position}"
        )
        company_present = any((company_name, external_id, website, address))
        contact_name = _mapped_value(row, mapping, "contact_name")
        email = _mapped_value(row, mapping, "contact_email").casefold()
        phone = _mapped_value(row, mapping, "contact_phone")
        contact_present = any((contact_name, email, phone))
        trade_present = any(_mapped_value(row, mapping, field) for field in _TRADE_FIELDS)
        if company_present:
            has_company = True
            company_keys.add(company_key)
            if external_id or _domain(website):
                high_keys.add(company_key)
            elif company_name and address:
                medium_keys.add(company_key)
        if contact_present:
            has_contact = True
            if _valid_email(email):
                contact_keys.add(f"email:{email}")
            else:
                contact_keys.add(f"company:{company_key}:name:{_normalized_token(contact_name)}")
        if trade_present:
            has_trade = True
            trade_records += 1
        if not any((company_present, contact_present, trade_present)):
            invalid_rows += 1
    kinds = sum((has_company, has_contact, has_trade))
    inferred: Literal["company", "contact", "shipment", "mixed", "unknown"]
    if kinds > 1:
        inferred = "mixed"
    elif has_company:
        inferred = "company"
    elif has_contact:
        inferred = "contact"
    elif has_trade:
        inferred = "shipment"
    else:
        inferred = "unknown"
    denominator = max(1, len(rows) - empty_rows)
    coverage = {
        "external_company_id": _coverage(rows, mapping, "external_company_id", denominator),
        "email": _coverage(rows, mapping, "contact_email", denominator),
        "website_domain": _coverage(rows, mapping, "website", denominator),
        "phone": round(
            sum(
                bool(
                    _mapped_value(row, mapping, "contact_phone")
                    or _mapped_value(row, mapping, "phone")
                )
                for row in rows
            )
            / denominator,
            4,
        ),
        "address": _coverage(rows, mapping, "address", denominator),
    }
    return _NetEaseAnalysis(
        inferred_data_type=inferred,
        empty_rows=empty_rows,
        invalid_rows=invalid_rows,
        company_count=len(company_keys),
        contact_count=len(contact_keys),
        trade_record_count=trade_records,
        coverage=coverage,
        high_confidence=len(high_keys),
        medium_confidence=len(medium_keys - high_keys),
    )


def _coverage(
    rows: Sequence[Mapping[str, str]],
    mapping: Mapping[str, str],
    logical_field: str,
    denominator: int,
) -> float:
    return round(
        sum(bool(_mapped_value(row, mapping, logical_field)) for row in rows) / denominator,
        4,
    )


def _read_tabular(
    file: BinaryIO,
    *,
    filename: str,
    allow_xlsx: bool,
) -> _TabularFile:
    data = _bounded_bytes(file)
    digest = hashlib.sha256(data).hexdigest()
    lowered = filename.casefold()
    if lowered.endswith(".xlsx"):
        if not allow_xlsx:
            raise AcceptancePreflightError(
                "acceptance_file_type_invalid", "This preflight accepts CSV only"
            )
        sheets = _xlsx_sheets(data)
        return _TabularFile(
            file_type="xlsx",
            file_size_bytes=len(data),
            file_sha256=digest,
            encoding="xlsx-xml",
            sheets=sheets,
        )
    if not lowered.endswith(".csv"):
        expected = "CSV or XLSX" if allow_xlsx else "CSV"
        raise AcceptancePreflightError(
            "acceptance_file_type_invalid", f"Preflight accepts {expected} files"
        )
    encoding = _detect_csv_encoding(data)
    sheet = _csv_sheet(data.decode(encoding))
    return _TabularFile(
        file_type="csv",
        file_size_bytes=len(data),
        file_sha256=digest,
        encoding=encoding,
        sheets=(sheet,),
    )


def _bounded_bytes(file: BinaryIO) -> bytes:
    file.seek(0)
    chunks: list[bytes] = []
    size = 0
    try:
        while chunk := file.read(64 * 1024):
            size += len(chunk)
            if size > ACCEPTANCE_MAX_BYTES:
                raise AcceptancePreflightError(
                    "acceptance_file_too_large",
                    f"File must not exceed {ACCEPTANCE_MAX_BYTES} bytes",
                )
            chunks.append(chunk)
    finally:
        file.seek(0)
    if size == 0:
        raise AcceptancePreflightError("acceptance_file_empty", "File must not be empty")
    return b"".join(chunks)


def _detect_csv_encoding(data: bytes) -> str:
    if data.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        try:
            data.decode("gb18030")
            return "gb18030"
        except UnicodeDecodeError as exc:
            raise AcceptancePreflightError(
                "acceptance_invalid_encoding",
                "CSV must use utf-8-sig, utf-8, or gb18030 encoding",
            ) from exc


def _csv_sheet(text: str) -> _Sheet:
    try:
        rows = [tuple(value for value in row) for row in csv.reader(io.StringIO(text), strict=True)]
    except csv.Error as exc:
        raise AcceptancePreflightError(
            "acceptance_malformed_csv", "CSV structure could not be parsed"
        ) from exc
    return _rows_to_sheet("CSV", rows, require_data=True)


def _xlsx_sheets(data: bytes) -> tuple[_Sheet, ...]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise AcceptancePreflightError(
            "acceptance_malformed_xlsx", "XLSX container could not be opened"
        ) from exc
    with archive:
        if sum(item.file_size for item in archive.infolist()) > XLSX_MAX_UNCOMPRESSED_BYTES:
            raise AcceptancePreflightError(
                "acceptance_xlsx_expanded_too_large", "Expanded XLSX content exceeds the limit"
            )
        try:
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            relationships = ElementTree.fromstring(
                archive.read("xl/_rels/workbook.xml.rels")
            )
        except (KeyError, ElementTree.ParseError) as exc:
            raise AcceptancePreflightError(
                "acceptance_malformed_xlsx", "XLSX workbook metadata is invalid"
            ) from exc
        relation_targets = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in relationships
            if "Id" in item.attrib and "Target" in item.attrib
        }
        shared_strings = _xlsx_shared_strings(archive)
        sheets: list[_Sheet] = []
        for sheet_node in workbook.findall("{*}sheets/{*}sheet"):
            name = sheet_node.attrib.get("name", "Sheet")
            relation_id = sheet_node.attrib.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            )
            target = relation_targets.get(relation_id or "")
            if target is None:
                continue
            member = target.lstrip("/")
            if not member.startswith("xl/"):
                member = f"xl/{member}"
            try:
                xml = ElementTree.fromstring(archive.read(member))
            except (KeyError, ElementTree.ParseError) as exc:
                raise AcceptancePreflightError(
                    "acceptance_malformed_xlsx", f"XLSX sheet metadata is invalid: {name}"
                ) from exc
            rows = _xlsx_rows(xml, shared_strings)
            if rows:
                sheets.append(_rows_to_sheet(name, rows, require_data=False))
        if not sheets:
            raise AcceptancePreflightError(
                "acceptance_file_empty", "XLSX must contain a non-empty worksheet"
            )
        total_rows = sum(len(sheet.rows) for sheet in sheets)
        if total_rows == 0:
            raise AcceptancePreflightError(
                "acceptance_file_empty", "XLSX must contain at least one data row"
            )
        if total_rows > ACCEPTANCE_MAX_ROWS:
            raise AcceptancePreflightError(
                "acceptance_too_many_rows",
                f"File must not exceed {ACCEPTANCE_MAX_ROWS} data rows",
            )
        return tuple(sheets)


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> tuple[str, ...]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return ()
    except ElementTree.ParseError as exc:
        raise AcceptancePreflightError(
            "acceptance_malformed_xlsx", "XLSX shared strings are invalid"
        ) from exc
    return tuple("".join(node.text or "" for node in item.findall(".//{*}t")) for item in root)


def _xlsx_rows(root: ElementTree.Element, shared_strings: tuple[str, ...]) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for row_node in root.findall(".//{*}sheetData/{*}row"):
        values: dict[int, str] = {}
        for cell in row_node.findall("{*}c"):
            reference = cell.attrib.get("r", "A")
            match = _CELL_REFERENCE.match(reference)
            if match is None:
                continue
            index = _column_index(match.group(1))
            cell_type = cell.attrib.get("t")
            if cell_type == "inlineStr":
                value = "".join(node.text or "" for node in cell.findall(".//{*}t"))
            else:
                value_node = cell.find("{*}v")
                value = value_node.text if value_node is not None and value_node.text else ""
                if cell_type == "s" and value:
                    try:
                        value = shared_strings[int(value)]
                    except (IndexError, ValueError) as exc:
                        raise AcceptancePreflightError(
                            "acceptance_malformed_xlsx", "XLSX shared string index is invalid"
                        ) from exc
                elif cell_type == "b":
                    value = "true" if value == "1" else "false"
            values[index] = value
        if values:
            rows.append(tuple(values.get(index, "") for index in range(max(values) + 1)))
        else:
            rows.append(())
    return rows


def _column_index(letters: str) -> int:
    value = 0
    for letter in letters:
        value = value * 26 + ord(letter) - ord("A") + 1
    return value - 1


def _rows_to_sheet(
    name: str,
    rows: Sequence[tuple[str, ...]],
    *,
    require_data: bool,
) -> _Sheet:
    header_index = next(
        (index for index, row in enumerate(rows) if any(value.strip() for value in row)),
        -1,
    )
    if header_index < 0:
        raise AcceptancePreflightError("acceptance_file_empty", "File has no header row")
    headers = tuple(value.strip() for value in rows[header_index])
    if not headers or any(not header for header in headers):
        raise AcceptancePreflightError(
            "acceptance_invalid_header", "Header names must not be empty"
        )
    data_rows = tuple(rows[header_index + 1 :])
    if require_data and not data_rows:
        raise AcceptancePreflightError(
            "acceptance_file_empty", "File must contain at least one data row"
        )
    if len(data_rows) > ACCEPTANCE_MAX_ROWS:
        raise AcceptancePreflightError(
            "acceptance_too_many_rows", f"File must not exceed {ACCEPTANCE_MAX_ROWS} data rows"
        )
    return _Sheet(name=name, headers=headers, rows=data_rows)


def _select_sheet(
    sheets: tuple[_Sheet, ...], aliases: Mapping[str, tuple[str, ...]]
) -> _Sheet:
    normalized_aliases = {
        _normalized_header(alias) for values in aliases.values() for alias in values
    }
    return max(
        sheets,
        key=lambda sheet: (
            sum(
                normalized in normalized_aliases
                for normalized in map(_normalized_header, sheet.headers)
            ),
            len(sheet.rows),
        ),
    )


def _infer_mapping(
    headers: tuple[str, ...],
    *,
    aliases: Mapping[str, tuple[str, ...]],
    manual_mapping: Mapping[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    invalid_fields = sorted(set(manual_mapping) - set(aliases))
    if invalid_fields:
        raise AcceptancePreflightError(
            "acceptance_mapping_invalid",
            f"Unsupported mapping fields: {', '.join(invalid_fields)}",
        )
    invalid_columns = sorted(
        {column for column in manual_mapping.values() if column not in headers}
    )
    if invalid_columns:
        raise AcceptancePreflightError(
            "acceptance_mapping_invalid",
            f"Mapped columns were not found: {', '.join(invalid_columns)}",
        )
    normalized_headers: dict[str, str] = {}
    for header in headers:
        normalized_headers.setdefault(_normalized_header(header), header)
    result = {field: column for field, column in manual_mapping.items()}
    confidence = {field: "manual" for field in manual_mapping}
    used_columns = set(result.values())
    for logical_field, candidates in aliases.items():
        if logical_field in result:
            continue
        for index, alias in enumerate(candidates):
            matched_header = normalized_headers.get(_normalized_header(alias))
            if matched_header is not None and matched_header not in used_columns:
                result[logical_field] = matched_header
                confidence[logical_field] = "high" if index == 0 else "medium"
                used_columns.add(matched_header)
                break
    return result, confidence


def _row_dicts(sheet: _Sheet) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            header: row[index].strip() if index < len(row) else ""
            for index, header in enumerate(sheet.headers)
        }
        for row in sheet.rows
    )


def _masked_samples(
    sheet: _Sheet,
    mapping: Mapping[str, str],
) -> dict[str, str]:
    """Return one deterministic, non-reversible display sample per mapped field."""
    rows = _row_dicts(sheet)
    samples: dict[str, str] = {}
    for logical_field, source_column in mapping.items():
        value = next(
            (
                row.get(source_column, "").strip()
                for row in rows
                if row.get(source_column, "").strip()
            ),
            "",
        )
        if value:
            samples[logical_field] = _mask_sample(logical_field, value)
    return samples


def _mask_sample(logical_field: str, value: str) -> str:
    if "email" in logical_field and "@" in value:
        local, domain = value.split("@", 1)
        domain_name, separator, suffix = domain.partition(".")
        return (
            f"{_mask_token(local)}@{_mask_token(domain_name)}"
            f"{separator}{suffix}"
        )
    if "phone" in logical_field:
        digits = "".join(character for character in value if character.isdigit())
        return f"••••{digits[-2:]}" if digits else "••••"
    if logical_field.endswith("_id") and len(value) > 8:
        return f"{value[:4]}••••{value[-4:]}"
    return _mask_token(value)


def _mask_token(value: str) -> str:
    compact = value.strip()
    if len(compact) <= 1:
        return "•"
    if len(compact) == 2:
        return f"{compact[0]}•"
    return f"{compact[0]}{'•' * min(6, len(compact) - 2)}{compact[-1]}"


def _mapped_value(
    row: Mapping[str, str], mapping: Mapping[str, str], logical_field: str
) -> str:
    column = mapping.get(logical_field)
    return row.get(column, "").strip() if column else ""


def _duplicates(headers: Sequence[str]) -> tuple[str, ...]:
    counts = Counter(_normalized_header(header) for header in headers)
    return tuple(
        header for header in headers if counts[_normalized_header(header)] > 1
    )


def _normalized_header(value: str) -> str:
    return _HEADER_NORMALIZER.sub("", value.strip().casefold())


def _normalized_token(value: str) -> str:
    return " ".join(_HEADER_NORMALIZER.sub(" ", value.strip().casefold()).split())


def _domain(value: str) -> str:
    candidate = value.strip().casefold()
    if not candidate:
        return ""
    candidate = candidate.split("://", 1)[-1].split("/", 1)[0].split("@")[-1]
    return candidate.removeprefix("www.") if "." in candidate else ""


def _valid_email(value: str) -> bool:
    return bool(_EMAIL_PATTERN.fullmatch(value.strip().casefold()))


def _valid_uuid(value: str) -> bool:
    try:
        UUID(value)
    except (ValueError, AttributeError):
        return False
    return True


def _normalize_event(value: str) -> str | None:
    return _EVENT_ALIASES.get(_normalized_token(value).replace(" ", "_"))


def _time_format(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return "missing"
    iso_candidate = cleaned.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(iso_candidate)
        return "iso8601"
    except ValueError:
        pass
    formats = (
        ("yyyy-mm-dd_hms", "%Y-%m-%d %H:%M:%S"),
        ("yyyy/mm/dd_hms", "%Y/%m/%d %H:%M:%S"),
        ("yyyy-mm-dd", "%Y-%m-%d"),
        ("us_slash_hms", "%m/%d/%Y %H:%M:%S"),
    )
    for label, pattern in formats:
        try:
            datetime.strptime(cleaned, pattern)
            return label
        except ValueError:
            continue
    return "unrecognized"
