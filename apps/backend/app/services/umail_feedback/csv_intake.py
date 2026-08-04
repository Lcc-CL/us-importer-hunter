"""Bounded standard-library CSV parser for Umail result files."""

import codecs
import csv
import hashlib
import io
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, BinaryIO

MAX_RESULT_CSV_BYTES = 20 * 1024 * 1024
MAX_RESULT_CSV_ROWS = 20_000
READ_CHUNK_BYTES = 64 * 1024

DEFAULT_RESULT_MAPPING = {
    "export_batch_id": "export_batch_id",
    "export_row_id": "export_row_id",
    "email": "email",
    "campaign": "campaign",
    "event_type": "event_type",
    "occurred_at": "occurred_at",
    "bounce_type": "bounce_type",
    "message_id": "message_id",
}
ALLOWED_RESULT_FIELDS = frozenset(DEFAULT_RESULT_MAPPING)
REQUIRED_RESULT_FIELDS = frozenset({"event_type", "occurred_at"})


class FeedbackCsvValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ParsedFeedbackCsv:
    file_size_bytes: int
    file_sha256: str
    encoding: str
    headers: tuple[str, ...]
    mapping_snapshot: dict[str, str]
    rows: tuple[dict[str, Any], ...]


class UmailResultCsvIntake:
    def parse(
        self,
        file: BinaryIO,
        *,
        mapping: dict[str, str],
    ) -> ParsedFeedbackCsv:
        data, digest, encoding = self._read_bytes(file)
        text = data.decode(encoding)
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = self._headers(reader.fieldnames)
        mapping_snapshot = self._mapping_snapshot(mapping, headers)
        rows: list[dict[str, Any]] = []
        try:
            for payload in reader:
                if len(rows) >= MAX_RESULT_CSV_ROWS:
                    raise FeedbackCsvValidationError(
                        "umail_result_too_many_rows",
                        f"CSV must not exceed {MAX_RESULT_CSV_ROWS} data rows",
                    )
                if None in payload:
                    raise FeedbackCsvValidationError(
                        "umail_result_column_count_mismatch",
                        "CSV row contains more values than the header",
                    )
                rows.append({key: value or "" for key, value in payload.items()})
        except csv.Error as exc:
            raise FeedbackCsvValidationError(
                "umail_result_malformed_csv", "CSV structure could not be parsed"
            ) from exc
        if not rows:
            raise FeedbackCsvValidationError(
                "umail_result_csv_empty", "CSV must contain at least one data row"
            )
        return ParsedFeedbackCsv(
            file_size_bytes=len(data),
            file_sha256=digest,
            encoding=encoding,
            headers=headers,
            mapping_snapshot=mapping_snapshot,
            rows=tuple(rows),
        )

    @staticmethod
    def _read_bytes(file: BinaryIO) -> tuple[bytes, str, str]:
        file.seek(0)
        chunks: list[bytes] = []
        digest = hashlib.sha256()
        size = 0
        while chunk := file.read(READ_CHUNK_BYTES):
            size += len(chunk)
            if size > MAX_RESULT_CSV_BYTES:
                file.seek(0)
                raise FeedbackCsvValidationError(
                    "umail_result_file_too_large",
                    f"CSV must not exceed {MAX_RESULT_CSV_BYTES} bytes",
                )
            chunks.append(chunk)
            digest.update(chunk)
        file.seek(0)
        if size == 0:
            raise FeedbackCsvValidationError(
                "umail_result_csv_empty", "CSV file must not be empty"
            )
        data = b"".join(chunks)
        encoding = "utf-8-sig" if data.startswith(codecs.BOM_UTF8) else "utf-8"
        try:
            data.decode(encoding)
        except UnicodeDecodeError as exc:
            raise FeedbackCsvValidationError(
                "umail_result_invalid_encoding", "CSV must use UTF-8 or UTF-8 BOM"
            ) from exc
        return data, digest.hexdigest(), encoding

    @staticmethod
    def _headers(fieldnames: Sequence[str] | None) -> tuple[str, ...]:
        if fieldnames is None:
            raise FeedbackCsvValidationError(
                "umail_result_invalid_header", "CSV must contain a header"
            )
        headers = tuple(fieldnames)
        if not headers or any(not header.strip() for header in headers):
            raise FeedbackCsvValidationError(
                "umail_result_invalid_header", "CSV header names must not be empty"
            )
        if len(headers) != len(set(headers)):
            raise FeedbackCsvValidationError(
                "umail_result_invalid_header", "CSV header names must be unique"
            )
        return headers

    @staticmethod
    def _mapping_snapshot(
        mapping: dict[str, str], headers: tuple[str, ...]
    ) -> dict[str, str]:
        invalid_fields = sorted(set(mapping) - ALLOWED_RESULT_FIELDS)
        if invalid_fields:
            raise FeedbackCsvValidationError(
                "umail_result_mapping_invalid",
                f"Unsupported mapping fields: {', '.join(invalid_fields)}",
            )
        snapshot = {**DEFAULT_RESULT_MAPPING, **mapping}
        invalid_columns = sorted(
            {
                column
                for field, column in mapping.items()
                if field in ALLOWED_RESULT_FIELDS and column not in headers
            }
        )
        if invalid_columns:
            raise FeedbackCsvValidationError(
                "umail_result_mapping_invalid",
                f"Mapped CSV columns were not found: {', '.join(invalid_columns)}",
            )
        missing_required = sorted(
            field for field in REQUIRED_RESULT_FIELDS if snapshot[field] not in headers
        )
        if missing_required:
            raise FeedbackCsvValidationError(
                "umail_result_mapping_invalid",
                f"Required mapped columns were not found: {', '.join(missing_required)}",
            )
        return snapshot
