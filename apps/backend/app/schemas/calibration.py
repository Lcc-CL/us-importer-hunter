"""Typed HTTP contracts for D4a quality calibration."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.prospect_batch import BatchSenderRequest
from app.workflows.calibration import (
    CalibrationEvaluationView,
    CalibrationReport,
)


class CalibrationCreateRequest(BaseModel):
    company_ids: list[UUID]
    sender: BatchSenderRequest | None = None


class CalibrationCreateResponse(BaseModel):
    calibration_id: UUID
    batch_id: UUID
    job_id: UUID
    status: str
    reused: bool


class CalibrationEvaluationRequest(BaseModel):
    research_accuracy: int = Field(ge=1, le=5)
    opportunity_reasonableness: int = Field(ge=1, le=5)
    contact_usability: int = Field(ge=1, le=5)
    draft_personalization: int = Field(ge=1, le=5)
    draft_professionalism: int = Field(ge=1, le=5)
    ready_for_real_outreach: bool
    reviewer_name: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)


class CalibrationEvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    research_accuracy: int
    opportunity_reasonableness: int
    contact_usability: int
    draft_personalization: int
    draft_professionalism: int
    ready_for_real_outreach: bool
    reviewer_name: str
    notes: str | None
    reviewed_at: datetime

    @classmethod
    def from_view(cls, value: CalibrationEvaluationView) -> "CalibrationEvaluationResponse":
        return cls.model_validate(value)


class ResearchMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_succeeded: bool
    pages_fetched: int
    duration_ms: int | None
    new_claim_count: int
    accepted_count: int
    edited_count: int
    rejected_count: int
    pending_count: int
    claims_without_source_count: int
    failure_reason: str | None


class OpportunityMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    generated: bool
    score: float | None
    qualification_decision: str | None
    major_positive_reasons: tuple[str, ...]
    major_deduction_reasons: tuple[str, ...]
    limiting_reasons: tuple[str, ...]
    trusted_evidence_count: int
    stopped_for_insufficient_evidence: bool


class ContactMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    personal_contact_found: bool
    department_contact_found: bool
    contact_type: str | None
    name: str | None
    title_or_department: str | None
    email: str | None
    phone: str | None
    source_url: str | None
    manually_confirmed: bool
    contact_not_found_reason: str | None


class DraftFactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    claim: str
    source_urls: tuple[str, ...]
    traceable_to_company_evidence: bool


class DraftMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    generated: bool
    not_generated_reason: str | None
    contact_type: str | None
    fact_count: int
    facts: tuple[DraftFactResponse, ...]
    all_facts_traceable: bool
    contains_unreviewed_claim: bool
    contains_rejected_claim: bool
    awaiting_human_review: bool
    explicitly_not_sent: bool


class WorkerMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    queue_wait_ms: int | None
    total_duration_ms: int | None
    stage_durations_ms: dict[str, int]
    attempt_count: int
    recovery_count: int
    lease_expired: bool
    duplicate_entity_count: int


class CalibrationCompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_id: UUID
    company_name: str
    final_status: str
    error_code: str | None
    error_summary: str | None
    research: ResearchMetricsResponse
    opportunity: OpportunityMetricsResponse
    contact: ContactMetricsResponse
    draft: DraftMetricsResponse
    worker: WorkerMetricsResponse
    evaluation: CalibrationEvaluationResponse | None


class CalibrationProviderMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    website_fetch_mode: str
    research_provider_mode: str
    draft_provider_mode: str
    contact_source_mode: str
    paid_request_count: int
    research_provider_call_count: int
    draft_provider_call_count: int
    provider_duration_ms: int
    token_usage_total: int | None


class CalibrationSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sample_count: int
    website_research_success_count: int
    website_research_success_rate: float
    evidence_review_company_count: int
    evidence_accepted_count: int
    evidence_rejected_count: int
    opportunity_generated_count: int
    opportunity_generation_rate: float
    qualified_count: int
    personal_contact_count: int
    personal_contact_coverage_rate: float
    department_contact_count: int
    department_contact_coverage_rate: float
    draft_generated_count: int
    draft_generation_rate: float
    ready_for_real_outreach_count: int
    evaluated_company_count: int
    worker_recovery_count: int
    average_processing_duration_ms: int | None
    average_research_accuracy: float | None
    average_opportunity_reasonableness: float | None
    average_contact_usability: float | None
    average_draft_personalization: float | None
    average_draft_professionalism: float | None


class CalibrationTruthChecksResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fabricated_contact_count: int
    unreviewed_fact_in_draft_count: int
    rejected_claim_in_score_or_draft_count: int
    pending_claim_bypassed_count: int
    draft_marked_sent_count: int
    duplicate_entity_count: int
    invalid_email_contact_count: int
    website_failure_mislabeled_company_missing_count: int
    opportunity_score_is_probability: bool


class CalibrationReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    calibration_id: UUID
    discovery_task_id: UUID
    prospect_batch_id: UUID
    status: str
    sample_source: str
    sample_reality_status: str
    created_at: datetime
    updated_at: datetime
    generated_at: datetime
    providers: CalibrationProviderMetricsResponse
    summary: CalibrationSummaryResponse
    truth_checks: CalibrationTruthChecksResponse
    companies: tuple[CalibrationCompanyResponse, ...]

    @classmethod
    def from_workflow(cls, report: CalibrationReport) -> "CalibrationReportResponse":
        return cls.model_validate(report)
