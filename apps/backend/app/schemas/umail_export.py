"""Typed HTTP contracts for D5d2a Umail export and suppression."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.umail_export import (
    SuppressionEntry,
    UmailExportBatch,
    UmailExportBatchStatus,
    UmailExportRow,
    UmailExportRowStatus,
)
from app.workflows.umail_export import SuppressionEntryPage, UmailExportSubmission


class SuppressionCreateRequest(BaseModel):
    email: str | None = Field(default=None, max_length=320)
    domain: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)
    source: str = Field(default="manual", min_length=1, max_length=100)
    created_by: str = Field(default="local_reviewer", min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_single_target(self) -> Self:
        targets = (self.email, self.domain, self.company)
        if sum(bool(value and value.strip()) for value in targets) != 1:
            raise ValueError("exactly one of email, domain, or company is required")
        return self

    @field_validator("reason", "source", "created_by")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        return value.strip()


class SuppressionDeactivateRequest(BaseModel):
    deactivated_by: str = Field(default="local_reviewer", min_length=1, max_length=160)

    @field_validator("deactivated_by")
    @classmethod
    def normalize_actor(cls, value: str) -> str:
        return value.strip()


class SuppressionEntryResponse(BaseModel):
    suppression_id: UUID
    email: str | None
    domain: str | None
    company: str | None
    active: bool
    reason: str
    source: str
    created_by: str
    deactivated_by: str | None
    deactivated_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, entry: SuppressionEntry) -> Self:
        return cls(
            suppression_id=entry.id,
            email=entry.email,
            domain=entry.domain,
            company=entry.company,
            active=entry.active,
            reason=entry.reason,
            source=entry.source,
            created_by=entry.created_by,
            deactivated_by=entry.deactivated_by,
            deactivated_at=entry.deactivated_at,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )


class SuppressionEntryListResponse(BaseModel):
    page: int
    limit: int
    total: int
    entries: list[SuppressionEntryResponse]

    @classmethod
    def from_page(cls, page: SuppressionEntryPage) -> Self:
        return cls(
            page=page.page,
            limit=page.limit,
            total=page.total,
            entries=[SuppressionEntryResponse.from_domain(entry) for entry in page.entries],
        )


class UmailExportCreateRequest(BaseModel):
    company_ids: list[UUID] = Field(min_length=1, max_length=500)
    campaign: str = Field(min_length=1, max_length=200)

    @field_validator("campaign")
    @classmethod
    def normalize_campaign(cls, value: str) -> str:
        return value.strip()


class UmailExportRowResponse(BaseModel):
    row_id: UUID
    position: int
    company_id: UUID
    contact_id: UUID | None
    company_name: str
    company_website: str | None
    contact_name: str | None
    contact_title: str | None
    contact_role: str | None
    contact_seniority: str | None
    is_department_contact: bool
    email: str | None
    route: str
    route_review_status: str
    pre_score: float
    status: UmailExportRowStatus
    exclusion_reason: str | None
    row_fingerprint: str

    @classmethod
    def from_domain(cls, row: UmailExportRow) -> Self:
        return cls(
            row_id=row.id,
            position=row.position,
            company_id=row.company_id,
            contact_id=row.contact_id,
            company_name=row.company_name,
            company_website=row.company_website,
            contact_name=row.contact_name,
            contact_title=row.contact_title,
            contact_role=row.contact_role,
            contact_seniority=row.contact_seniority,
            is_department_contact=row.is_department_contact,
            email=row.email,
            route=row.route.value,
            route_review_status=row.route_review_status.value,
            pre_score=row.pre_score,
            status=row.status,
            exclusion_reason=row.exclusion_reason,
            row_fingerprint=row.row_fingerprint,
        )


class UmailExportBatchResponse(BaseModel):
    batch_id: UUID
    routing_run_id: UUID
    execution_generation: int
    campaign: str
    mapping_version: str
    selection_hash: str
    status: UmailExportBatchStatus
    total_rows: int
    ready_count: int
    suppressed_count: int
    invalid_count: int
    duplicate_count: int
    content_sha256: str
    downloaded_at: datetime | None
    created_at: datetime
    updated_at: datetime
    reused: bool
    sent: bool = False
    rows: list[UmailExportRowResponse]

    @classmethod
    def from_submission(cls, submission: UmailExportSubmission) -> Self:
        return cls.from_domain(
            submission.batch,
            submission.rows,
            reused=submission.reused,
        )

    @classmethod
    def from_domain(
        cls,
        batch: UmailExportBatch,
        rows: tuple[UmailExportRow, ...],
        *,
        reused: bool,
    ) -> Self:
        return cls(
            batch_id=batch.id,
            routing_run_id=batch.routing_run_id,
            execution_generation=batch.execution_generation,
            campaign=batch.campaign,
            mapping_version=batch.mapping_version,
            selection_hash=batch.selection_hash,
            status=batch.status,
            total_rows=batch.total_rows,
            ready_count=batch.ready_count,
            suppressed_count=batch.suppressed_count,
            invalid_count=batch.invalid_count,
            duplicate_count=batch.duplicate_count,
            content_sha256=batch.content_sha256,
            downloaded_at=batch.downloaded_at,
            created_at=batch.created_at,
            updated_at=batch.updated_at,
            reused=reused,
            sent=False,
            rows=[UmailExportRowResponse.from_domain(row) for row in rows],
        )
