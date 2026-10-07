"""Typed HTTP contracts for traceable raw bulk imports."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.bulk_import import ImportSession, ImportSessionStatus, RawImportRow
from app.workflows.bulk_import import BulkImportOutcome, RawImportRowPage


class ImportSessionResponse(BaseModel):
    session_id: UUID
    source: str
    original_filename: str
    file_type: str
    file_size_bytes: int
    file_sha256: str
    mapping_json: dict[str, Any]
    encoding: str
    status: ImportSessionStatus
    total_rows: int
    accepted_rows: int
    invalid_rows: int
    duplicate_rows: int
    started_at: datetime | None
    completed_at: datetime | None
    error_summary: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, session: ImportSession) -> "ImportSessionResponse":
        return cls(
            session_id=session.id,
            source=session.source,
            original_filename=session.original_filename,
            file_type=session.file_type,
            file_size_bytes=session.file_size_bytes,
            file_sha256=session.file_sha256,
            mapping_json=session.mapping_json,
            encoding=session.encoding,
            status=session.status,
            total_rows=session.total_rows,
            accepted_rows=session.accepted_rows,
            invalid_rows=session.invalid_rows,
            duplicate_rows=session.duplicate_rows,
            started_at=session.started_at,
            completed_at=session.completed_at,
            error_summary=session.error_summary,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )


class ImportSessionCreateResponse(ImportSessionResponse):
    reused_existing: bool

    @classmethod
    def from_outcome(cls, outcome: BulkImportOutcome) -> "ImportSessionCreateResponse":
        return cls(
            **ImportSessionResponse.from_domain(outcome.session).model_dump(),
            reused_existing=outcome.reused_existing,
        )


class RawImportRowResponse(BaseModel):
    id: UUID
    row_number: int
    raw_payload: dict[str, Any]
    row_hash: str
    status: str
    error_codes: list[str]
    created_at: datetime

    @classmethod
    def from_domain(cls, row: RawImportRow) -> "RawImportRowResponse":
        return cls(
            id=row.id,
            row_number=row.row_number,
            raw_payload=row.raw_payload,
            row_hash=row.row_hash,
            status=row.status.value,
            error_codes=list(row.error_codes),
            created_at=row.created_at,
        )


class RawImportRowListResponse(BaseModel):
    session_id: UUID
    page: int = Field(ge=1)
    limit: int = Field(ge=1, le=200)
    total: int = Field(ge=0)
    rows: list[RawImportRowResponse]

    @classmethod
    def from_page(cls, result: RawImportRowPage) -> "RawImportRowListResponse":
        return cls(
            session_id=result.session_id,
            page=result.page,
            limit=result.limit,
            total=result.total,
            rows=[RawImportRowResponse.from_domain(row) for row in result.rows],
        )
