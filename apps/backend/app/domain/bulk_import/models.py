"""Pure domain state for traceable raw CSV intake.

The intake boundary records observations only. It never creates Company,
Contact, Opportunity, Research, Outreach, or Import Evidence aggregates.
"""

import dataclasses
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.exceptions import DomainError, InvalidStateTransition


class ImportSessionStatus(StrEnum):
    RECEIVING = "receiving"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"


class RawImportRowStatus(StrEnum):
    ACCEPTED = "accepted"
    INVALID = "invalid"
    DUPLICATE = "duplicate"


@dataclasses.dataclass(frozen=True)
class RawImportRow:
    id: UUID
    import_session_id: UUID
    row_number: int
    raw_payload: dict[str, Any]
    row_hash: str
    status: RawImportRowStatus
    error_codes: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if self.row_number < 2:
            raise DomainError("raw import row number must be at least 2")
        if len(self.row_hash) != 64:
            raise DomainError("raw import row hash must be a SHA-256 hex digest")
        if self.status is RawImportRowStatus.ACCEPTED and self.error_codes:
            raise DomainError("accepted raw import rows cannot contain error codes")
        if self.status is not RawImportRowStatus.ACCEPTED and not self.error_codes:
            raise DomainError("non-accepted raw import rows require error codes")

    @classmethod
    def create(
        cls,
        *,
        import_session_id: UUID,
        row_number: int,
        raw_payload: dict[str, Any],
        row_hash: str,
        status: RawImportRowStatus,
        error_codes: tuple[str, ...] = (),
    ) -> "RawImportRow":
        return cls(
            id=uuid4(),
            import_session_id=import_session_id,
            row_number=row_number,
            raw_payload=raw_payload,
            row_hash=row_hash,
            status=status,
            error_codes=error_codes,
            created_at=utcnow(),
        )


class ImportSession:
    def __init__(
        self,
        *,
        id: UUID,
        source: str,
        original_filename: str,
        file_type: str,
        file_size_bytes: int,
        file_sha256: str,
        mapping_json: dict[str, Any],
        encoding: str,
        status: ImportSessionStatus,
        total_rows: int,
        accepted_rows: int,
        invalid_rows: int,
        duplicate_rows: int,
        started_at: datetime | None,
        completed_at: datetime | None,
        error_summary: str | None,
        created_at: datetime,
        updated_at: datetime,
    ) -> None:
        self._id = id
        self._source = source
        self._original_filename = original_filename
        self._file_type = file_type
        self._file_size_bytes = file_size_bytes
        self._file_sha256 = file_sha256
        self._mapping_json = dict(mapping_json)
        self._encoding = encoding
        self._status = status
        self._total_rows = total_rows
        self._accepted_rows = accepted_rows
        self._invalid_rows = invalid_rows
        self._duplicate_rows = duplicate_rows
        self._started_at = started_at
        self._completed_at = completed_at
        self._error_summary = error_summary
        self._created_at = created_at
        self._updated_at = updated_at
        self._validate()

    @classmethod
    def create(
        cls,
        *,
        source: str,
        original_filename: str,
        file_size_bytes: int,
        file_sha256: str,
        mapping_json: dict[str, Any],
        encoding: str,
    ) -> "ImportSession":
        now = utcnow()
        return cls(
            id=uuid4(),
            source=source,
            original_filename=original_filename,
            file_type="csv",
            file_size_bytes=file_size_bytes,
            file_sha256=file_sha256,
            mapping_json=mapping_json,
            encoding=encoding,
            status=ImportSessionStatus.RECEIVING,
            total_rows=0,
            accepted_rows=0,
            invalid_rows=0,
            duplicate_rows=0,
            started_at=None,
            completed_at=None,
            error_summary=None,
            created_at=now,
            updated_at=now,
        )

    def start_processing(self) -> None:
        if self._status is not ImportSessionStatus.RECEIVING:
            raise InvalidStateTransition(
                f"cannot start an import session in {self._status.value} status"
            )
        now = utcnow()
        self._status = ImportSessionStatus.PROCESSING
        self._started_at = now
        self._updated_at = now

    def record_progress(
        self,
        *,
        total_rows: int,
        accepted_rows: int,
        invalid_rows: int,
        duplicate_rows: int,
    ) -> None:
        if self._status is not ImportSessionStatus.PROCESSING:
            raise InvalidStateTransition(
                f"cannot record progress for {self._status.value} import session"
            )
        if total_rows < self._total_rows:
            raise DomainError("import progress cannot move backwards")
        self._set_counts(
            total_rows=total_rows,
            accepted_rows=accepted_rows,
            invalid_rows=invalid_rows,
            duplicate_rows=duplicate_rows,
        )
        self._updated_at = utcnow()

    def complete(self) -> None:
        if self._status is not ImportSessionStatus.PROCESSING:
            raise InvalidStateTransition(
                f"cannot complete an import session in {self._status.value} status"
            )
        if self._total_rows == 0:
            raise DomainError("cannot complete an import session with no rows")
        now = utcnow()
        self._status = (
            ImportSessionStatus.PARTIAL_FAILED
            if self._invalid_rows > 0
            else ImportSessionStatus.COMPLETED
        )
        self._completed_at = now
        self._updated_at = now

    def fail(self, error_summary: str) -> None:
        if self._status in {
            ImportSessionStatus.COMPLETED,
            ImportSessionStatus.PARTIAL_FAILED,
            ImportSessionStatus.FAILED,
        }:
            raise InvalidStateTransition(
                f"cannot fail an import session in {self._status.value} status"
            )
        summary = error_summary.strip()
        if not summary:
            raise DomainError("failed import session requires an error summary")
        now = utcnow()
        self._status = ImportSessionStatus.FAILED
        self._error_summary = summary
        self._completed_at = now
        self._updated_at = now

    def _set_counts(
        self,
        *,
        total_rows: int,
        accepted_rows: int,
        invalid_rows: int,
        duplicate_rows: int,
    ) -> None:
        counts = (total_rows, accepted_rows, invalid_rows, duplicate_rows)
        if any(value < 0 for value in counts):
            raise DomainError("import row counts cannot be negative")
        if accepted_rows + invalid_rows + duplicate_rows != total_rows:
            raise DomainError("import row counts must add up to total rows")
        self._total_rows = total_rows
        self._accepted_rows = accepted_rows
        self._invalid_rows = invalid_rows
        self._duplicate_rows = duplicate_rows

    def _validate(self) -> None:
        if not self._source.strip():
            raise DomainError("import source must not be empty")
        if not self._original_filename.strip():
            raise DomainError("original filename must not be empty")
        if self._file_type != "csv":
            raise DomainError("D5a1 import session only supports csv")
        if self._file_size_bytes <= 0:
            raise DomainError("import file size must be positive")
        if len(self._file_sha256) != 64:
            raise DomainError("import file hash must be a SHA-256 hex digest")
        self._set_counts(
            total_rows=self._total_rows,
            accepted_rows=self._accepted_rows,
            invalid_rows=self._invalid_rows,
            duplicate_rows=self._duplicate_rows,
        )

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def source(self) -> str:
        return self._source

    @property
    def original_filename(self) -> str:
        return self._original_filename

    @property
    def file_type(self) -> str:
        return self._file_type

    @property
    def file_size_bytes(self) -> int:
        return self._file_size_bytes

    @property
    def file_sha256(self) -> str:
        return self._file_sha256

    @property
    def mapping_json(self) -> dict[str, Any]:
        return dict(self._mapping_json)

    @property
    def encoding(self) -> str:
        return self._encoding

    @property
    def status(self) -> ImportSessionStatus:
        return self._status

    @property
    def total_rows(self) -> int:
        return self._total_rows

    @property
    def accepted_rows(self) -> int:
        return self._accepted_rows

    @property
    def invalid_rows(self) -> int:
        return self._invalid_rows

    @property
    def duplicate_rows(self) -> int:
        return self._duplicate_rows

    @property
    def started_at(self) -> datetime | None:
        return self._started_at

    @property
    def completed_at(self) -> datetime | None:
        return self._completed_at

    @property
    def error_summary(self) -> str | None:
        return self._error_summary

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at
