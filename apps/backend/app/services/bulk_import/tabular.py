"""Unified tabular reader abstraction for raw import intake.

CSV and XLSX files are reduced to the same row unit — ``TabularRow`` — so
ImportSession / RawImportRow persistence never has to care about the source
file format. XLSX parsing additionally captures workbook structure (merged
cells) that deterministic contact inheritance relies on.

Accepted debt (D5e2b.1): XLSX is parsed as a bounded in-memory batch, not a
true streaming pipeline. The MVP row cap (20k) makes streaming ETL
unjustified today.
"""

from __future__ import annotations

import codecs
import csv
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, BinaryIO, Literal

MAX_TABULAR_BYTES = 20 * 1024 * 1024
MAX_TABULAR_ROWS = 20_000
XLSX_MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024

_XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_CELL_REFERENCE = re.compile(r"([A-Z]+)(\d+)")
_HEADER_NORMALIZER = re.compile(r"[\s_\-./()（）]+")
_CURRENCY_PATTERN = re.compile(r"(?i)(cny|rmb|usd|eur|jpy|gbp|元|¥|€|\$)")

#: Fields that identify a company row (an anchor) when mapped and non-empty.
COMPANY_IDENTITY_FIELDS = ("company_name", "external_company_id", "website", "address")
#: Fields that only exist in transaction-level shipment rows.
SHIPMENT_TICKET_FIELDS = ("shipment_date", "quantity", "weight", "pol", "pod")
#: Fields that describe a company-level import summary, not one shipment.
SUMMARY_TRADE_FIELDS = (
    "hs_code",
    "product_description",
    "supplier",
    "amount",
    "last_import_at",
)

ALLOWED_LOGICAL_FIELDS = frozenset(
    {
        "company_name",
        "external_company_id",
        "website",
        "address",
        "country",
        "company_type",
        "phone",
        "contact_name",
        "contact_email",
        "contact_phone",
        "contact_title",
        "contact_linkedin",
        "product_description",
        "hs_code",
        "supplier",
        "origin_country",
        "shipment_date",
        "quantity",
        "weight",
        "amount",
        "last_import_at",
        "pol",
        "pod",
    }
)


class TabularValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class TabularPreflight:
    file_size_bytes: int
    file_sha256: str
    encoding: str
    file_type: Literal["csv", "xlsx"]
    headers: tuple[str, ...]
    total_rows: int
    sheet_name: str


@dataclass(frozen=True)
class TabularRow:
    row_number: int
    sheet_name: str
    raw_payload: dict[str, Any]


def _normalized_header(value: str) -> str:
    return _HEADER_NORMALIZER.sub("", value.strip().casefold())


def _bounded_bytes(file: BinaryIO) -> bytes:
    file.seek(0)
    chunks: list[bytes] = []
    size = 0
    while chunk := file.read(READ_CHUNK_BYTES):
        size += len(chunk)
        if size > MAX_TABULAR_BYTES:
            file.seek(0)
            raise TabularValidationError(
                "bulk_import_file_too_large",
                f"File must not exceed {MAX_TABULAR_BYTES} bytes",
            )
        chunks.append(chunk)
    file.seek(0)
    if size == 0:
        raise TabularValidationError("bulk_import_file_empty", "File must not be empty")
    return b"".join(chunks)


def _scan_csv(file: BinaryIO, *, encoding: str) -> tuple[tuple[str, ...], int]:
    file.seek(0)
    wrapper = io.TextIOWrapper(file, encoding=encoding, newline="")
    try:
        reader = csv.reader(wrapper, strict=True)
        try:
            header_values = next(reader)
        except StopIteration as exc:
            raise TabularValidationError(
                "bulk_import_csv_empty", "CSV file must contain a header and data rows"
            ) from exc
        headers = tuple(header_values)
        if not headers or any(not header.strip() for header in headers):
            raise TabularValidationError(
                "bulk_import_invalid_header", "CSV header names must not be empty"
            )
        if len(set(headers)) != len(headers):
            raise TabularValidationError(
                "bulk_import_invalid_header", "CSV header names must be unique"
            )
        total_rows = 0
        for _values in reader:
            total_rows += 1
            if total_rows > MAX_TABULAR_ROWS:
                raise TabularValidationError(
                    "bulk_import_too_many_rows",
                    f"File must not exceed {MAX_TABULAR_ROWS} data rows",
                )
        if total_rows == 0:
            raise TabularValidationError(
                "bulk_import_csv_empty", "CSV file must contain at least one data row"
            )
        return headers, total_rows
    except csv.Error as exc:
        raise TabularValidationError(
            "bulk_import_malformed_csv", "CSV structure could not be parsed"
        ) from exc
    finally:
        wrapper.detach()
        file.seek(0)


def _validate_mapping(mapping: Mapping[str, str], headers: tuple[str, ...]) -> None:
    invalid_keys = sorted(set(mapping) - ALLOWED_LOGICAL_FIELDS)
    if invalid_keys:
        raise TabularValidationError(
            "bulk_import_mapping_invalid",
            f"Unsupported logical mapping fields: {', '.join(invalid_keys)}",
        )
    invalid_columns = sorted({column for column in mapping.values() if column not in headers})
    if invalid_columns:
        raise TabularValidationError(
            "bulk_import_mapping_invalid",
            f"Mapped columns were not found: {', '.join(invalid_columns)}",
        )


def _raw_payload(headers: tuple[str, ...], values: list[str], *, sheet_name: str) -> dict[str, Any]:
    fields = {
        header: values[index] if index < len(values) else None
        for index, header in enumerate(headers)
    }
    payload: dict[str, Any] = {"fields": fields, "values": list(values), "sheet": sheet_name}
    if len(values) > len(headers):
        payload["extra_values"] = values[len(headers) :]
    if len(values) < len(headers):
        payload["missing_fields"] = list(headers[len(values) :])
    return payload


def _detect_currency(raw_amount: str) -> str:
    match = _CURRENCY_PATTERN.search(raw_amount)
    if not match:
        return "unknown"
    token = match.group(1).casefold()
    if token in {"cny", "rmb", "元", "¥"}:
        return "cny"
    if token == "eur" or token == "€":
        return "eur"
    if token == "usd":
        return "usd"
    if token == "jpy":
        return "jpy"
    if token == "gbp":
        return "gbp"
    # A bare "$" is ambiguous (USD/CAD/AUD/...); never assume.
    return "unknown"


def annotate_company_import_summary(
    payload: dict[str, Any],
    *,
    mapping: Mapping[str, str],
) -> None:
    """Tag company-level import-summary rows without fabricating shipments.

    A row with summary trade fields (HS, product, supplier, value) but no
    per-ticket shipment fields is a company import summary, never a shipment.
    Amounts with no explicit currency stay raw and are marked unknown.
    """
    fields = payload.get("fields", {})
    has_summary = any(
        bool((fields.get(column) or "").strip())
        for field in SUMMARY_TRADE_FIELDS
        if (column := mapping.get(field))
    )
    has_ticket = any(
        bool((fields.get(column) or "").strip())
        for field in SHIPMENT_TICKET_FIELDS
        if (column := mapping.get(field))
    )
    if has_summary and not has_ticket:
        payload["record_kind"] = "company_import_summary"
        last_import_column = mapping.get("last_import_at")
        if last_import_column:
            last_import = (fields.get(last_import_column) or "").strip()
            if last_import:
                payload["last_import_at"] = last_import
        amount_column = mapping.get("amount")
        if amount_column:
            raw_amount = (fields.get(amount_column) or "").strip()
            if raw_amount:
                payload["import_value_raw"] = raw_amount
                payload["currency"] = _detect_currency(raw_amount)


class CsvTabularReader:
    """CSV reader: bounded multi-pass scan, streaming row iteration."""

    def preflight(self, file: BinaryIO, *, mapping: Mapping[str, str]) -> TabularPreflight:
        size, digest, encoding = self._scan_bytes(file)
        headers, total_rows = _scan_csv(file, encoding=encoding)
        _validate_mapping(mapping, headers)
        return TabularPreflight(
            file_size_bytes=size,
            file_sha256=digest,
            encoding=encoding,
            file_type="csv",
            headers=headers,
            total_rows=total_rows,
            sheet_name="CSV",
        )

    def iter_rows(
        self,
        file: BinaryIO,
        *,
        preflight: TabularPreflight,
        mapping: Mapping[str, str],
    ) -> Iterator[TabularRow]:
        file.seek(0)
        wrapper = io.TextIOWrapper(file, encoding=preflight.encoding, newline="")
        try:
            reader = csv.reader(wrapper, strict=True)
            next(reader)
            for values in reader:
                payload = _raw_payload(
                    preflight.headers,
                    list(values),
                    sheet_name=preflight.sheet_name,
                )
                annotate_company_import_summary(payload, mapping=mapping)
                yield TabularRow(
                    row_number=reader.line_num,
                    sheet_name=preflight.sheet_name,
                    raw_payload=payload,
                )
        finally:
            wrapper.detach()
            file.seek(0)

    @staticmethod
    def _scan_bytes(file: BinaryIO) -> tuple[int, str, str]:
        try:
            data = _bounded_bytes(file)
        except TabularValidationError as exc:
            if exc.code == "bulk_import_file_empty":
                raise TabularValidationError(
                    "bulk_import_csv_empty", "CSV file must not be empty"
                ) from exc
            raise
        digest = hashlib.sha256(data).hexdigest()
        if data.startswith(codecs.BOM_UTF8):
            encoding = "utf-8-sig"
        else:
            try:
                data.decode("utf-8")
                encoding = "utf-8"
            except UnicodeDecodeError:
                try:
                    data.decode("gb18030")
                    encoding = "gb18030"
                except UnicodeDecodeError as exc:
                    raise TabularValidationError(
                        "bulk_import_invalid_encoding",
                        "CSV must use utf-8-sig, utf-8, or gb18030 encoding",
                    ) from exc
        return len(data), digest, encoding


class XlsxTabularReader:
    """XLSX reader: bounded zip/XML parse with merged-cell contact inheritance."""

    def preflight(self, file: BinaryIO, *, mapping: Mapping[str, str]) -> TabularPreflight:
        data = _bounded_bytes(file)
        digest = hashlib.sha256(data).hexdigest()
        sheet, headers, total_rows = self._read_sheet(data)
        _validate_mapping(mapping, headers)
        return TabularPreflight(
            file_size_bytes=len(data),
            file_sha256=digest,
            encoding="xlsx-xml",
            file_type="xlsx",
            headers=headers,
            total_rows=total_rows,
            sheet_name=sheet,
        )

    def iter_rows(
        self,
        file: BinaryIO,
        *,
        preflight: TabularPreflight,
        mapping: Mapping[str, str],
    ) -> Iterator[TabularRow]:
        data = _bounded_bytes(file)
        rows, merges = self._read_rows(data, preflight.sheet_name)
        anchors = _company_anchor_rows(rows, mapping, preflight.headers)
        rows_by_number = {row_number: cells for row_number, cells in rows}
        for row_number, cells in rows:
            if row_number <= 1:
                continue
            values, payload = self._row_payload(
                cells,
                headers=preflight.headers,
                sheet_name=preflight.sheet_name,
            )
            _apply_inheritance(
                payload,
                row_number=row_number,
                rows_by_number=rows_by_number,
                anchors=anchors,
                merges=merges,
                mapping=mapping,
                headers=preflight.headers,
            )
            annotate_company_import_summary(payload, mapping=mapping)
            yield TabularRow(
                row_number=row_number,
                sheet_name=preflight.sheet_name,
                raw_payload=payload,
            )

    @staticmethod
    def _read_sheet(data: bytes) -> tuple[str, tuple[str, ...], int]:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            _validate_xlsx_archive(archive)
            try:
                workbook = ET.fromstring(archive.read("xl/workbook.xml"))
                relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            except (KeyError, ET.ParseError) as exc:
                raise TabularValidationError(
                    "bulk_import_malformed_xlsx", "XLSX workbook metadata is invalid"
                ) from exc
            relation_targets = {
                item.attrib["Id"]: item.attrib["Target"]
                for item in relationships
                if "Id" in item.attrib and "Target" in item.attrib
            }
            sheet_nodes = workbook.findall(f"{{{_XLSX_NS}}}sheets/{{{_XLSX_NS}}}sheet")
            for sheet_node in sheet_nodes:
                name = sheet_node.attrib.get("name", "Sheet")
                relation_id = sheet_node.attrib.get(f"{{{_REL_NS}}}id")
                target = relation_targets.get(relation_id or "")
                if not target:
                    continue
                member = target.lstrip("/")
                if not member.startswith("xl/"):
                    member = f"xl/{member}"
                try:
                    sheet_xml = archive.read(member)
                except KeyError:
                    continue
                rows, _merges = XlsxTabularReader._parse_sheet(sheet_xml)
                data_rows = [r for r in rows if r[0] > 1]
                if not data_rows:
                    continue
                headers = XlsxTabularReader._headers_from_rows(rows)
                if not headers or any(not header.strip() for header in headers):
                    raise TabularValidationError(
                        "bulk_import_invalid_header", "XLSX header names must not be empty"
                    )
                if len(set(headers)) != len(headers):
                    raise TabularValidationError(
                        "bulk_import_invalid_header", "XLSX header names must be unique"
                    )
                if len(data_rows) > MAX_TABULAR_ROWS:
                    raise TabularValidationError(
                        "bulk_import_too_many_rows",
                        f"File must not exceed {MAX_TABULAR_ROWS} data rows",
                    )
                return name, headers, len(data_rows)
        raise TabularValidationError(
            "bulk_import_xlsx_empty", "XLSX must contain a non-empty worksheet"
        )

    @staticmethod
    def _read_rows(
        data: bytes,
        sheet_name: str,
    ) -> tuple[list[tuple[int, dict[str, str]]], list[tuple[int, int, str]]]:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            _validate_xlsx_archive(archive)
            try:
                workbook = ET.fromstring(archive.read("xl/workbook.xml"))
                relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            except (KeyError, ET.ParseError) as exc:
                raise TabularValidationError(
                    "bulk_import_malformed_xlsx", "XLSX workbook metadata is invalid"
                ) from exc
            relation_targets = {
                item.attrib["Id"]: item.attrib["Target"]
                for item in relationships
                if "Id" in item.attrib and "Target" in item.attrib
            }
            for sheet_node in workbook.findall(f"{{{_XLSX_NS}}}sheets/{{{_XLSX_NS}}}sheet"):
                name = sheet_node.attrib.get("name", "Sheet")
                if name != sheet_name:
                    continue
                relation_id = sheet_node.attrib.get(f"{{{_REL_NS}}}id")
                target = relation_targets.get(relation_id or "")
                if not target:
                    continue
                member = target.lstrip("/")
                if not member.startswith("xl/"):
                    member = f"xl/{member}"
                return XlsxTabularReader._parse_sheet(archive.read(member))
        raise TabularValidationError(
            "bulk_import_malformed_xlsx", f"XLSX sheet not found: {sheet_name}"
        )

    @staticmethod
    def _parse_sheet(
        sheet_xml: bytes,
    ) -> tuple[list[tuple[int, dict[str, str]]], list[tuple[int, int, str]]]:
        root = ET.fromstring(sheet_xml)
        rows: list[tuple[int, dict[str, str]]] = []
        merges: list[tuple[int, int, str]] = []
        for row_node in root.findall(f".//{{{_XLSX_NS}}}row"):
            if row_node.attrib.get("hidden") == "1":
                continue
            row_number = int(row_node.attrib.get("r", "0"))
            cells: dict[str, str] = {}
            for cell in row_node.findall(f"{{{_XLSX_NS}}}c"):
                match = _CELL_REFERENCE.match(cell.attrib.get("r", ""))
                if match is None:
                    continue
                column = match.group(1)
                value = XlsxTabularReader._cell_value(cell)
                if value:
                    cells[column] = value
            if row_number:
                rows.append((row_number, cells))
        for merge in root.findall(f".//{{{_XLSX_NS}}}mergeCell"):
            ref = merge.attrib.get("ref", "")
            match = re.match(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$", ref)
            if match:
                col1, row1, _col2, row2 = match.groups()
                merges.append((int(row1), int(row2), col1))
        return rows, merges

    @staticmethod
    def _cell_value(cell: ET.Element) -> str:
        value_node = cell.find(f"{{{_XLSX_NS}}}v")
        if value_node is not None and value_node.text:
            return value_node.text.strip()
        inline = cell.find(f"{{{_XLSX_NS}}}is")
        if inline is not None:
            return "".join(
                text.text or "" for text in inline.iter(f"{{{_XLSX_NS}}}t")
            ).strip()
        return ""

    @staticmethod
    def _headers_from_rows(rows: list[tuple[int, dict[str, str]]]) -> tuple[str, ...]:
        header_row = next((cells for row_number, cells in rows if row_number == 1), None)
        if header_row is None:
            return ()
        max_column = 0
        for column in header_row:
            index = _column_index(column)
            max_column = max(max_column, index)
        return tuple(header_row.get(_column_name(index), "") for index in range(max_column + 1))

    @staticmethod
    def _row_payload(
        cells: dict[str, str],
        *,
        headers: tuple[str, ...],
        sheet_name: str,
    ) -> tuple[list[str], dict[str, Any]]:
        values: list[str] = []
        extra: list[str] = []
        for column, value in sorted(cells.items(), key=lambda item: _column_index(item[0])):
            index = _column_index(column)
            if index < len(headers):
                while len(values) < index:
                    values.append("")
                values.append(value)
            else:
                extra.append(value)
        while len(values) < len(headers):
            values.append("")
        payload = _raw_payload(headers, values, sheet_name=sheet_name)
        if extra:
            payload["extra_values"] = extra
        return values, payload


def _validate_xlsx_archive(archive: zipfile.ZipFile) -> None:
    if sum(item.file_size for item in archive.infolist()) > XLSX_MAX_UNCOMPRESSED_BYTES:
        raise TabularValidationError(
            "bulk_import_xlsx_expanded_too_large",
            "Expanded XLSX content exceeds the limit",
        )
    try:
        if archive.read("xl/workbook.xml") is None:  # pragma: no cover - validation only
            pass
    except KeyError as exc:
        raise TabularValidationError(
            "bulk_import_malformed_xlsx", "XLSX workbook metadata is invalid"
        ) from exc


def _column_index(column: str) -> int:
    result = 0
    for char in column:
        result = result * 26 + (ord(char) - ord("A") + 1)
    return result - 1


def _column_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _company_anchor_rows(
    rows: list[tuple[int, dict[str, str]]],
    mapping: Mapping[str, str],
    headers: tuple[str, ...],
) -> set[int]:
    company_columns = _company_column_letters(mapping, headers)
    anchors: set[int] = set()
    for row_number, cells in rows:
        if any((cells.get(column) or "").strip() for column in company_columns):
            anchors.add(row_number)
    return anchors


def _apply_inheritance(
    payload: dict[str, Any],
    *,
    row_number: int,
    rows_by_number: dict[int, dict[str, str]],
    anchors: set[int],
    merges: list[tuple[int, int, str]],
    mapping: Mapping[str, str],
    headers: tuple[str, ...],
) -> None:
    """Inherit company identity from a merged-cell anchor when structure proves it."""
    company_columns = _company_column_letters(mapping, headers)
    has_identity = bool(anchors and row_number in anchors)
    if has_identity:
        payload["company_anchor_row"] = row_number
        return

    anchor_row = _merged_anchor_for(row_number, company_columns, merges)
    if anchor_row is not None and anchor_row in anchors:
        anchor_cells = rows_by_number.get(anchor_row, {})
        fields = payload.get("fields", {})
        inherited: list[str] = []
        for column in sorted(company_columns):
            header = _column_index(column)
            if header >= len(headers):
                continue
            header_name = headers[header]
            if not (fields.get(header_name) or "").strip():
                inherited_value = (anchor_cells.get(column) or "").strip()
                if inherited_value:
                    fields[header_name] = inherited_value
                    inherited.append(header_name)
        payload["inherited_company_source_row"] = anchor_row
        if inherited:
            payload["inherited_fields"] = inherited
        payload["grouping_rule"] = "xlsx_vertical_merge"
        payload["grouping_confidence"] = "high"
        payload["company_anchor_row"] = anchor_row
        return
    payload["grouping_rule"] = "none"
    payload["grouping_confidence"] = "low"
    payload["company_review_required"] = True


def _company_column_letters(
    mapping: Mapping[str, str],
    headers: tuple[str, ...],
) -> set[str]:
    return {
        _column_name(headers.index(mapping[field]))
        for field in COMPANY_IDENTITY_FIELDS
        if field in mapping and mapping[field] in headers
    }


def _merged_anchor_for(
    row_number: int,
    company_columns: set[str],
    merges: list[tuple[int, int, str]],
) -> int | None:
    candidates: list[int] = []
    for start, end, column in merges:
        if end > start and start < row_number <= end:
            if not company_columns or column in company_columns:
                candidates.append(start)
    return min(candidates) if candidates else None


def reader_for(filename: str) -> CsvTabularReader | XlsxTabularReader:
    lowered = filename.casefold()
    if lowered.endswith(".xlsx"):
        return XlsxTabularReader()
    if lowered.endswith(".csv"):
        return CsvTabularReader()
    raise TabularValidationError(
        "bulk_import_file_type_invalid", "Formal import accepts .csv or .xlsx files"
    )


def reader_for_type(file_type: str) -> CsvTabularReader | XlsxTabularReader:
    if file_type == "xlsx":
        return XlsxTabularReader()
    return CsvTabularReader()


def hash_row_values(values: list[str]) -> str:
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
