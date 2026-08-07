"""Raw import intake over the unified CSV/XLSX tabular readers.

The legacy ``StreamingCsvIntake`` keeps its exact public contract and now
delegates to the CSV reader; ``BulkTabularIntake`` selects the reader by file
type so ImportSession / RawImportRow persistence is format-agnostic.
"""

from collections.abc import Iterator, Mapping
from typing import BinaryIO
from uuid import UUID

from app.domain.bulk_import import RawImportRow, RawImportRowStatus
from app.services.bulk_import.tabular import (
    CsvTabularReader,
    TabularPreflight,
    TabularRow,
    TabularValidationError,
    XlsxTabularReader,
    hash_row_values,
    reader_for,
    reader_for_type,
)

CSV_BATCH_SIZE = 500
MAX_CSV_BYTES = 20 * 1024 * 1024
MAX_CSV_ROWS = 20_000

# Backward-compatible name: the unified reader raises TabularValidationError.
BulkCsvValidationError = TabularValidationError


def _row_errors(values: list[str], *, expected_columns: int) -> tuple[str, ...]:
    errors: list[str] = []
    if not values or not any(value.strip() for value in values):
        errors.append("empty_row")
    if len(values) != expected_columns:
        errors.append("column_count_mismatch")
    return tuple(errors)


def _classify_rows(
    rows: Iterator[TabularRow],
    *,
    session_id: UUID,
    preflight: TabularPreflight,
) -> Iterator[RawImportRow]:
    seen_hashes: set[str] = set()
    for row in rows:
        values = list(row.raw_payload.get("values", []))
        row_hash = hash_row_values(values)
        errors = _row_errors(values, expected_columns=len(preflight.headers))
        if row_hash in seen_hashes:
            status = RawImportRowStatus.DUPLICATE
            errors = (*errors, "duplicate_row")
        elif errors:
            status = RawImportRowStatus.INVALID
        else:
            status = RawImportRowStatus.ACCEPTED
        seen_hashes.add(row_hash)
        yield RawImportRow.create(
            import_session_id=session_id,
            row_number=row.row_number,
            raw_payload=row.raw_payload,
            row_hash=row_hash,
            status=status,
            error_codes=errors,
        )


class StreamingCsvIntake:
    """Legacy CSV-only intake, backed by the unified CSV reader."""

    def __init__(self, reader: CsvTabularReader | None = None) -> None:
        self._reader = reader or CsvTabularReader()

    def preflight(self, file: BinaryIO, *, mapping: Mapping[str, str]) -> TabularPreflight:
        return self._reader.preflight(file, mapping=mapping)

    def iter_batches(
        self,
        file: BinaryIO,
        *,
        session_id: UUID,
        preflight: TabularPreflight,
        mapping: Mapping[str, str] | None = None,
    ) -> Iterator[tuple[RawImportRow, ...]]:
        mapping = mapping or {}
        rows = self._reader.iter_rows(file, preflight=preflight, mapping=mapping)
        batch: list[RawImportRow] = []
        for row in _classify_rows(rows, session_id=session_id, preflight=preflight):
            batch.append(row)
            if len(batch) == CSV_BATCH_SIZE:
                yield tuple(batch)
                batch.clear()
        if batch:
            yield tuple(batch)


class BulkTabularIntake:
    """Format-agnostic intake: dispatches to the CSV or XLSX tabular reader."""

    def __init__(
        self,
        csv_reader: CsvTabularReader | None = None,
        xlsx_reader: XlsxTabularReader | None = None,
    ) -> None:
        self._csv_reader = csv_reader or CsvTabularReader()
        self._xlsx_reader = xlsx_reader or XlsxTabularReader()

    def _reader(self, file_type: str) -> CsvTabularReader | XlsxTabularReader:
        if file_type == "xlsx":
            return self._xlsx_reader
        return self._csv_reader

    def preflight(
        self,
        file: BinaryIO,
        *,
        mapping: Mapping[str, str],
        filename: str,
    ) -> TabularPreflight:
        reader = reader_for(filename)
        if isinstance(reader, XlsxTabularReader):
            return self._xlsx_reader.preflight(file, mapping=mapping)
        return self._csv_reader.preflight(file, mapping=mapping)

    def iter_batches(
        self,
        file: BinaryIO,
        *,
        session_id: UUID,
        preflight: TabularPreflight,
        mapping: Mapping[str, str],
    ) -> Iterator[tuple[RawImportRow, ...]]:
        reader = reader_for_type(preflight.file_type)
        rows = reader.iter_rows(file, preflight=preflight, mapping=mapping)
        batch: list[RawImportRow] = []
        for row in _classify_rows(rows, session_id=session_id, preflight=preflight):
            batch.append(row)
            if len(batch) == CSV_BATCH_SIZE:
                yield tuple(batch)
                batch.clear()
        if batch:
            yield tuple(batch)
