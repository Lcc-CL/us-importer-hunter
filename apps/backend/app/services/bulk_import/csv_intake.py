"""Streaming, standard-library-only CSV raw intake.

The parser intentionally performs bounded multi-pass reads over the uploaded
spooled file: bytes are hashed and encoding-validated without retaining file
content, CSV structure and row limits are preflighted before a session is
created, then rows are emitted in fixed-size batches for PostgreSQL writes.
"""

import codecs
import csv
import hashlib
import io
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, BinaryIO
from uuid import UUID

from app.domain.bulk_import import RawImportRow, RawImportRowStatus

MAX_CSV_BYTES = 20 * 1024 * 1024
MAX_CSV_ROWS = 20_000
CSV_BATCH_SIZE = 500
READ_CHUNK_BYTES = 64 * 1024

ALLOWED_LOGICAL_FIELDS = frozenset(
    {
        "company_name",
        "external_company_id",
        "website",
        "address",
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
        "pol",
        "pod",
    }
)


class BulkCsvValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class CsvPreflight:
    file_size_bytes: int
    file_sha256: str
    encoding: str
    headers: tuple[str, ...]
    total_rows: int


class StreamingCsvIntake:
    def preflight(
        self,
        file: BinaryIO,
        *,
        mapping: Mapping[str, str],
    ) -> CsvPreflight:
        size, digest, encoding = self._scan_bytes(file)
        headers, total_rows = self._scan_csv(file, encoding=encoding)
        self._validate_mapping(mapping, headers)
        return CsvPreflight(
            file_size_bytes=size,
            file_sha256=digest,
            encoding=encoding,
            headers=headers,
            total_rows=total_rows,
        )

    def iter_batches(
        self,
        file: BinaryIO,
        *,
        session_id: UUID,
        preflight: CsvPreflight,
    ) -> Iterator[tuple[RawImportRow, ...]]:
        file.seek(0)
        wrapper = io.TextIOWrapper(file, encoding=preflight.encoding, newline="")
        seen_hashes: set[str] = set()
        batch: list[RawImportRow] = []
        try:
            reader = csv.reader(wrapper, strict=True)
            next(reader)
            for values in reader:
                row_number = reader.line_num
                row_hash = self._hash_row(values)
                errors = self._row_errors(values, expected_columns=len(preflight.headers))
                if row_hash in seen_hashes:
                    status = RawImportRowStatus.DUPLICATE
                    errors = (*errors, "duplicate_row")
                elif errors:
                    status = RawImportRowStatus.INVALID
                else:
                    status = RawImportRowStatus.ACCEPTED
                seen_hashes.add(row_hash)
                batch.append(
                    RawImportRow.create(
                        import_session_id=session_id,
                        row_number=row_number,
                        raw_payload=self._raw_payload(preflight.headers, values),
                        row_hash=row_hash,
                        status=status,
                        error_codes=errors,
                    )
                )
                if len(batch) == CSV_BATCH_SIZE:
                    yield tuple(batch)
                    batch.clear()
            if batch:
                yield tuple(batch)
        finally:
            wrapper.detach()
            file.seek(0)

    def _scan_bytes(self, file: BinaryIO) -> tuple[int, str, str]:
        file.seek(0)
        digest = hashlib.sha256()
        utf8_decoder = codecs.getincrementaldecoder("utf-8")()
        utf8_valid = True
        size = 0
        first_bytes = b""
        while chunk := file.read(READ_CHUNK_BYTES):
            if not first_bytes:
                first_bytes = chunk[:3]
            size += len(chunk)
            if size > MAX_CSV_BYTES:
                file.seek(0)
                raise BulkCsvValidationError(
                    "bulk_import_file_too_large",
                    f"CSV file must not exceed {MAX_CSV_BYTES} bytes",
                )
            digest.update(chunk)
            if utf8_valid:
                try:
                    utf8_decoder.decode(chunk, final=False)
                except UnicodeDecodeError:
                    utf8_valid = False
        if size == 0:
            file.seek(0)
            raise BulkCsvValidationError("bulk_import_csv_empty", "CSV file must not be empty")
        if utf8_valid:
            try:
                utf8_decoder.decode(b"", final=True)
            except UnicodeDecodeError:
                utf8_valid = False

        if first_bytes.startswith(codecs.BOM_UTF8):
            encoding = "utf-8-sig"
        elif utf8_valid:
            encoding = "utf-8"
        else:
            self._validate_encoding(file, "gb18030")
            encoding = "gb18030"
        file.seek(0)
        return size, digest.hexdigest(), encoding

    @staticmethod
    def _validate_encoding(file: BinaryIO, encoding: str) -> None:
        file.seek(0)
        decoder = codecs.getincrementaldecoder(encoding)()
        try:
            while chunk := file.read(READ_CHUNK_BYTES):
                decoder.decode(chunk, final=False)
            decoder.decode(b"", final=True)
        except UnicodeDecodeError as exc:
            raise BulkCsvValidationError(
                "bulk_import_invalid_encoding",
                "CSV must use utf-8-sig, utf-8, or gb18030 encoding",
            ) from exc
        finally:
            file.seek(0)

    @staticmethod
    def _scan_csv(file: BinaryIO, *, encoding: str) -> tuple[tuple[str, ...], int]:
        file.seek(0)
        wrapper = io.TextIOWrapper(file, encoding=encoding, newline="")
        try:
            reader = csv.reader(wrapper, strict=True)
            try:
                header_values = next(reader)
            except StopIteration as exc:
                raise BulkCsvValidationError(
                    "bulk_import_csv_empty", "CSV file must contain a header and data rows"
                ) from exc
            headers = tuple(header_values)
            if not headers or any(not header.strip() for header in headers):
                raise BulkCsvValidationError(
                    "bulk_import_invalid_header",
                    "CSV header names must not be empty",
                )
            if len(set(headers)) != len(headers):
                raise BulkCsvValidationError(
                    "bulk_import_invalid_header",
                    "CSV header names must be unique",
                )
            total_rows = 0
            for _values in reader:
                total_rows += 1
                if total_rows > MAX_CSV_ROWS:
                    raise BulkCsvValidationError(
                        "bulk_import_too_many_rows",
                        f"CSV must not exceed {MAX_CSV_ROWS} data rows",
                    )
            if total_rows == 0:
                raise BulkCsvValidationError(
                    "bulk_import_csv_empty", "CSV file must contain at least one data row"
                )
            return headers, total_rows
        except csv.Error as exc:
            raise BulkCsvValidationError(
                "bulk_import_malformed_csv", "CSV structure could not be parsed"
            ) from exc
        finally:
            wrapper.detach()
            file.seek(0)

    @staticmethod
    def _validate_mapping(mapping: Mapping[str, str], headers: tuple[str, ...]) -> None:
        invalid_keys = sorted(set(mapping) - ALLOWED_LOGICAL_FIELDS)
        if invalid_keys:
            raise BulkCsvValidationError(
                "bulk_import_mapping_invalid",
                f"Unsupported logical mapping fields: {', '.join(invalid_keys)}",
            )
        invalid_columns = sorted({column for column in mapping.values() if column not in headers})
        if invalid_columns:
            raise BulkCsvValidationError(
                "bulk_import_mapping_invalid",
                f"Mapped CSV columns were not found: {', '.join(invalid_columns)}",
            )

    @staticmethod
    def _hash_row(values: list[str]) -> str:
        payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_errors(values: list[str], *, expected_columns: int) -> tuple[str, ...]:
        errors: list[str] = []
        if not values or not any(value.strip() for value in values):
            errors.append("empty_row")
        if len(values) != expected_columns:
            errors.append("column_count_mismatch")
        return tuple(errors)

    @staticmethod
    def _raw_payload(headers: tuple[str, ...], values: list[str]) -> dict[str, Any]:
        fields = {
            header: values[index] if index < len(values) else None
            for index, header in enumerate(headers)
        }
        payload: dict[str, Any] = {"fields": fields, "values": list(values)}
        if len(values) > len(headers):
            payload["extra_values"] = values[len(headers) :]
        if len(values) < len(headers):
            payload["missing_fields"] = list(headers[len(values) :])
        return payload
