"""HTTP contracts for the D2 batch prospect pipeline."""

from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from app.domain.prospect_batch import ProspectBatch, ProspectBatchCompany
from app.domain.prospect_job import ProspectJob
from app.domain.services import SenderProfile
from app.workflows.prospect_batch import ProspectCompanyBlockers

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class BatchSenderRequest(BaseModel):
    name: NonBlank
    company: NonBlank
    value_proposition: NonBlank

    def to_domain(self) -> SenderProfile:
        return SenderProfile(
            name=self.name,
            company=self.company,
            value_proposition=self.value_proposition,
        )


class ProspectBatchCreateRequest(BaseModel):
    company_ids: list[UUID]
    limit: int = 5
    sender: BatchSenderRequest | None = None


class ProspectBatchCreateResponse(BaseModel):
    batch_id: UUID
    job_id: UUID
    status: str
    reused: bool


class ProspectBatchExecutionResponse(BaseModel):
    job_id: UUID
    batch_id: UUID
    status: str
    available_at: datetime
    attempt_count: int
    max_attempts: int
    heartbeat_at: datetime | None
    last_error_code: str | None
    last_error_summary: str | None
    recovery_count: int
    last_recovered_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    @classmethod
    def from_domain(cls, job: ProspectJob) -> Self:
        return cls(
            job_id=job.id,
            batch_id=job.batch_id,
            status=job.status.value,
            available_at=job.available_at,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            heartbeat_at=job.heartbeat_at,
            last_error_code=job.last_error_code,
            last_error_summary=job.last_error_summary,
            recovery_count=job.recovery_count,
            last_recovered_at=job.last_recovered_at,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            updated_at=job.updated_at,
        )


class ProspectBatchRetryRequest(BaseModel):
    sender: BatchSenderRequest | None = None


class ProspectBatchResumeRequest(BaseModel):
    sender: BatchSenderRequest | None = None


class ProspectBatchResponse(BaseModel):
    batch_id: UUID
    discovery_task_id: UUID | None
    routing_run_id: UUID | None
    requested_count: int
    effective_count: int
    status: str
    queued_count: int
    running_count: int
    completed_count: int
    needs_review_count: int
    failed_count: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_summary: str | None

    @classmethod
    def from_domain(cls, batch: ProspectBatch) -> Self:
        return cls(
            batch_id=batch.id,
            discovery_task_id=batch.discovery_task_id,
            routing_run_id=batch.routing_run_id,
            requested_count=batch.requested_count,
            effective_count=batch.effective_count,
            status=batch.status.value,
            queued_count=batch.queued_count,
            running_count=batch.running_count,
            completed_count=batch.completed_count,
            needs_review_count=batch.needs_review_count,
            failed_count=batch.failed_count,
            created_at=batch.created_at,
            started_at=batch.started_at,
            completed_at=batch.completed_at,
            error_summary=batch.error_summary,
        )


class ProspectBatchCompanyResponse(BaseModel):
    company_id: UUID
    company_name: str
    position: int
    pipeline_version: str
    current_stage: str
    status: str
    research_id: UUID | None
    opportunity_id: UUID | None
    selected_contact_id: UUID | None
    outreach_id: UUID | None
    draft_version: int | None
    draft_id: str | None
    score: float | None
    qualification_decision: str | None
    reasons: list[str]
    contact_name: str | None
    contact_email: str | None
    contact_source_url: str | None
    draft_subject: str | None
    draft_status: str | None
    error_code: str | None
    error_summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    blocking_claim_count: int
    resumed_at: datetime | None
    resumed_from_stage: str | None
    resume_count: int

    @classmethod
    def from_domain(cls, company: ProspectBatchCompany) -> Self:
        draft_id = (
            f"{company.outreach_id}:{company.draft_version}"
            if company.outreach_id is not None and company.draft_version is not None
            else None
        )
        return cls(
            company_id=company.company_id,
            company_name=company.company_name,
            position=company.position,
            pipeline_version=company.pipeline_version,
            current_stage=company.current_stage.value,
            status=company.status.value,
            research_id=company.research_id,
            opportunity_id=company.opportunity_id,
            selected_contact_id=company.selected_contact_id,
            outreach_id=company.outreach_id,
            draft_version=company.draft_version,
            draft_id=draft_id,
            score=company.score,
            qualification_decision=company.qualification_decision,
            reasons=list(company.reasons),
            contact_name=company.contact_name,
            contact_email=company.contact_email,
            contact_source_url=company.contact_source_url,
            draft_subject=company.draft_subject,
            draft_status=company.draft_status,
            error_code=company.error_code,
            error_summary=company.error_summary,
            started_at=company.started_at,
            completed_at=company.completed_at,
            blocking_claim_count=company.blocking_claim_count,
            resumed_at=company.resumed_at,
            resumed_from_stage=(
                company.resumed_from_stage.value if company.resumed_from_stage else None
            ),
            resume_count=company.resume_count,
        )


class ProspectBatchCompanyListResponse(BaseModel):
    batch_id: UUID
    companies: list[ProspectBatchCompanyResponse] = Field(default_factory=list)


class EvidenceBlockerResponse(BaseModel):
    claim_position: int
    status: str
    decision: str | None
    kind: str
    detail: str
    evidence_snippet: str
    source_url: str
    fetched_at: datetime
    confidence: float


class ProspectCompanyBlockersResponse(BaseModel):
    batch_id: UUID
    company_id: UUID
    research_id: UUID
    blocking_claim_count: int
    pending_claim_count: int
    claims: list[EvidenceBlockerResponse]

    @classmethod
    def from_workflow(cls, blockers: ProspectCompanyBlockers) -> Self:
        return cls(
            batch_id=blockers.batch_id,
            company_id=blockers.company_id,
            research_id=blockers.research_id,
            blocking_claim_count=blockers.blocking_claim_count,
            pending_claim_count=blockers.pending_claim_count,
            claims=[
                EvidenceBlockerResponse(
                    claim_position=claim.claim_position,
                    status=claim.status,
                    decision=claim.decision,
                    kind=claim.kind,
                    detail=claim.detail,
                    evidence_snippet=claim.evidence_snippet,
                    source_url=claim.source_url,
                    fetched_at=claim.fetched_at,
                    confidence=claim.confidence,
                )
                for claim in blockers.claims
            ],
        )
