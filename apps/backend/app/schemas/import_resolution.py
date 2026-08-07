"""Typed API contracts for D5b1 import entity resolution."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.import_resolution import (
    ImportDecisionView,
    ImportEntityDecision,
    ImportEntityDecisionKind,
    ImportEntityReviewStatus,
    ImportEntityType,
    ImportJobStatus,
    ImportProcessingJob,
    ImportResolution,
    ImportResolutionStatus,
    ImportReviewAction,
)
from app.workflows.import_resolution import ImportDecisionPage


class ImportResolutionStartResponse(BaseModel):
    session_id: UUID
    processing_job_id: UUID
    status: ImportJobStatus
    reused: bool


class ImportResolutionResponse(BaseModel):
    session_id: UUID
    processing_job_id: UUID | None
    processing_status: ImportJobStatus | None
    resolution_status: ImportResolutionStatus
    total_rows: int
    processed_rows: int
    companies_created: int
    companies_reused: int
    company_reviews_required: int
    contacts_created: int
    contacts_reused: int
    company_contacts_created: int
    invalid_rows: int
    failed_rows: int
    attempt_count: int
    max_attempts: int
    heartbeat_at: datetime | None
    last_error_code: str | None
    last_error_summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    @classmethod
    def from_domain(
        cls,
        resolution: ImportResolution,
        job: ImportProcessingJob | None,
    ) -> "ImportResolutionResponse":
        return cls(
            session_id=resolution.import_session_id,
            processing_job_id=job.id if job else None,
            processing_status=job.status if job else None,
            resolution_status=resolution.status,
            total_rows=resolution.total_rows,
            processed_rows=resolution.processed_rows,
            companies_created=resolution.companies_created,
            companies_reused=resolution.companies_reused,
            company_reviews_required=resolution.company_reviews_required,
            contacts_created=resolution.contacts_created,
            contacts_reused=resolution.contacts_reused,
            company_contacts_created=resolution.company_contacts_created,
            invalid_rows=resolution.invalid_rows,
            failed_rows=resolution.failed_rows,
            attempt_count=job.attempt_count if job else 0,
            max_attempts=job.max_attempts if job else 0,
            heartbeat_at=job.heartbeat_at if job else None,
            last_error_code=job.last_error_code if job else None,
            last_error_summary=job.last_error_summary if job else None,
            started_at=resolution.started_at,
            completed_at=resolution.completed_at,
            updated_at=resolution.updated_at,
        )


class ImportEntityDecisionResponse(BaseModel):
    decision_id: UUID
    session_id: UUID
    raw_import_row_id: UUID
    row_number: int | None = None
    source_label: str | None = None
    entity_type: ImportEntityType
    candidate_entity_id: UUID | None
    candidate_label: str | None = None
    decision: ImportEntityDecisionKind
    confidence: float
    reason_codes: list[str]
    review_status: ImportEntityReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    source_facts: dict[str, str] = Field(default_factory=dict)
    is_department_contact: bool = False

    @classmethod
    def from_domain(
        cls,
        decision: ImportEntityDecision,
        *,
        view: ImportDecisionView | None = None,
    ) -> "ImportEntityDecisionResponse":
        return cls(
            decision_id=decision.id,
            session_id=decision.import_session_id,
            raw_import_row_id=decision.raw_import_row_id,
            row_number=view.row_number if view else None,
            source_label=view.source_label if view else None,
            entity_type=decision.entity_type,
            candidate_entity_id=decision.candidate_entity_id,
            candidate_label=view.candidate_label if view else None,
            decision=decision.decision,
            confidence=decision.confidence,
            reason_codes=list(decision.reason_codes),
            review_status=decision.review_status,
            reviewed_by=decision.reviewed_by,
            reviewed_at=decision.reviewed_at,
            created_at=decision.created_at,
            updated_at=decision.updated_at,
            source_facts=view.source_facts if view else {},
            is_department_contact=view.is_department_contact if view else False,
        )


class ImportEntityDecisionListResponse(BaseModel):
    session_id: UUID
    page: int = Field(ge=1)
    limit: int = Field(ge=1, le=200)
    total: int = Field(ge=0)
    decisions: list[ImportEntityDecisionResponse]

    @classmethod
    def from_page(cls, page: ImportDecisionPage) -> "ImportEntityDecisionListResponse":
        return cls(
            session_id=page.session_id,
            page=page.page,
            limit=page.limit,
            total=page.total,
            decisions=[
                ImportEntityDecisionResponse.from_domain(view.decision, view=view)
                for view in page.decisions
            ],
        )


class ImportEntityReviewRequest(BaseModel):
    action: ImportReviewAction
    reviewed_by: str = Field(default="local_reviewer", min_length=1, max_length=160)
