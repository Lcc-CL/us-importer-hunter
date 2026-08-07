"""Typed HTTP contracts for D5c prospect routing."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.domain.import_resolution import ImportJobStatus, ImportProcessingJob
from app.domain.prospect_routing import (
    ProspectRoute,
    ProspectRouteReviewAction,
    ProspectRouteReviewStatus,
    ProspectRoutingCriteria,
    ProspectRoutingRun,
    ProspectRoutingRunStatus,
    ProspectTier,
)
from app.shared.exceptions import InvalidInputError
from app.workflows.prospect_routing import ProspectRoutePage


class ProspectRoutingCriteriaRequest(BaseModel):
    target_product_keywords: list[str] = Field(default_factory=list, max_length=50)
    target_hs_codes: list[str] = Field(default_factory=list, max_length=50)
    preferred_origin_countries: list[str] = Field(default_factory=list, max_length=50)
    preferred_pol: list[str] = Field(default_factory=list, max_length=50)
    preferred_pod: list[str] = Field(default_factory=list, max_length=50)

    @field_validator(
        "target_product_keywords",
        "target_hs_codes",
        "preferred_origin_countries",
        "preferred_pol",
        "preferred_pod",
    )
    @classmethod
    def normalize_values(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


class ProspectRoutingCreateRequest(BaseModel):
    criteria: ProspectRoutingCriteriaRequest
    campaign_name: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)

    def to_domain(self) -> ProspectRoutingCriteria:
        if (
            not self.criteria.target_product_keywords
            and not self.criteria.target_hs_codes
        ):
            raise InvalidInputError(
                code="ROUTING_TARGET_REQUIRED",
                message="target_product_keywords or target_hs_codes is required",
            )
        return ProspectRoutingCriteria(
            target_product_keywords=tuple(self.criteria.target_product_keywords),
            target_hs_codes=tuple(self.criteria.target_hs_codes),
            preferred_origin_countries=tuple(
                self.criteria.preferred_origin_countries
            ),
            preferred_pol=tuple(self.criteria.preferred_pol),
            preferred_pod=tuple(self.criteria.preferred_pod),
            campaign_name=_clean_optional(self.campaign_name),
            notes=_clean_optional(self.notes),
        )


class ProspectRoutingCreateResponse(BaseModel):
    routing_run_id: UUID
    processing_job_id: UUID
    status: ImportJobStatus
    reused: bool
    recalculated: bool


class RoutingPreviewCompany(BaseModel):
    company_id: UUID
    company_name: str
    tier: str
    pre_score: float
    reason_codes: list[str]
    positive_reasons: list[str]
    unknown_evidence: list[str]
    explicit_negative: list[str]
    product_signal: bool
    hs_signal: bool
    import_signal: bool
    contact_quality: float
    data_completeness: float
    person_contact_count: int
    department_contact_count: int
    rules_version: str


class RoutingPreviewResponse(BaseModel):
    import_session_id: UUID
    rules_version: str
    taxonomy_version: str
    preview_valid: bool
    entity_pending_count: int
    totals: dict[str, int]
    companies: list[RoutingPreviewCompany]


class ProspectRoutingRunResponse(BaseModel):
    routing_run_id: UUID
    import_session_id: UUID
    processing_job_id: UUID | None
    processing_status: ImportJobStatus | None
    status: ProspectRoutingRunStatus
    rules_version: str
    execution_generation: int
    current_execution_generation: int
    available_generations: list[int]
    criteria: dict[str, object]
    weights_snapshot: dict[str, object]
    total_companies: int
    routed_companies: int
    blocked_companies: int
    tier_a_count: int
    tier_b_count: int
    tier_c_count: int
    tier_d_count: int
    attempt_count: int
    max_attempts: int
    heartbeat_at: datetime | None
    last_error_code: str | None
    last_error_summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    error_summary: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(
        cls,
        run: ProspectRoutingRun,
        job: ImportProcessingJob | None,
        available_generations: tuple[int, ...],
    ) -> Self:
        return cls(
            routing_run_id=run.id,
            import_session_id=run.import_session_id,
            processing_job_id=job.id if job else None,
            processing_status=job.status if job else None,
            status=run.status,
            rules_version=run.rules_version,
            execution_generation=run.execution_generation,
            current_execution_generation=run.execution_generation,
            available_generations=list(available_generations),
            criteria=run.criteria_json,
            weights_snapshot=run.weights_snapshot_json,
            total_companies=run.total_companies,
            routed_companies=run.routed_companies,
            blocked_companies=run.blocked_companies,
            tier_a_count=run.tier_a_count,
            tier_b_count=run.tier_b_count,
            tier_c_count=run.tier_c_count,
            tier_d_count=run.tier_d_count,
            attempt_count=job.attempt_count if job else 0,
            max_attempts=job.max_attempts if job else 0,
            heartbeat_at=job.heartbeat_at if job else None,
            last_error_code=job.last_error_code if job else None,
            last_error_summary=job.last_error_summary if job else None,
            started_at=run.started_at,
            completed_at=run.completed_at,
            error_summary=run.error_summary,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )


class ProspectRouteResponse(BaseModel):
    route_id: UUID
    routing_run_id: UUID
    execution_generation: int
    company_id: UUID
    company_name: str
    pre_score: float
    recommended_tier: ProspectTier | None
    effective_tier: ProspectTier | None
    feature_snapshot: dict[str, object]
    reason_codes: list[str]
    warning_codes: list[str]
    review_status: ProspectRouteReviewStatus
    override_reason: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    contact_count: int
    has_usable_contact: bool
    has_usable_email: bool
    preferred_role_category: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, route: ProspectRoute) -> Self:
        return cls(
            route_id=route.id,
            routing_run_id=route.routing_run_id,
            execution_generation=route.execution_generation,
            company_id=route.company_id,
            company_name=route.company_name,
            pre_score=route.pre_score,
            recommended_tier=route.recommended_tier,
            effective_tier=route.effective_tier,
            feature_snapshot=route.feature_snapshot_json,
            reason_codes=list(route.reason_codes),
            warning_codes=list(route.warning_codes),
            review_status=route.review_status,
            override_reason=route.override_reason,
            reviewed_by=route.reviewed_by,
            reviewed_at=route.reviewed_at,
            contact_count=route.contact_count,
            has_usable_contact=route.has_usable_contact,
            has_usable_email=route.has_usable_email,
            preferred_role_category=route.preferred_role_category,
            created_at=route.created_at,
            updated_at=route.updated_at,
        )


class ProspectRouteListResponse(BaseModel):
    routing_run_id: UUID
    execution_generation: int
    page: int
    limit: int
    total: int
    routes: list[ProspectRouteResponse]

    @classmethod
    def from_page(cls, page: ProspectRoutePage) -> Self:
        return cls(
            routing_run_id=page.routing_run_id,
            execution_generation=page.execution_generation,
            page=page.page,
            limit=page.limit,
            total=page.total,
            routes=[ProspectRouteResponse.from_domain(route) for route in page.routes],
        )


class ProspectRouteReviewRequest(BaseModel):
    action: ProspectRouteReviewAction
    effective_tier: ProspectTier | None = None
    override_reason: str | None = Field(default=None, max_length=2000)
    reviewed_by: str = Field(default="local_reviewer", min_length=1, max_length=160)

    @field_validator("override_reason")
    @classmethod
    def normalize_override_reason(cls, value: str | None) -> str | None:
        return _clean_optional(value)

    @field_validator("reviewed_by")
    @classmethod
    def normalize_reviewer(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("reviewed_by must not be blank")
        return clean


class ProspectRoutingBatchCreateRequest(BaseModel):
    company_ids: list[UUID] = Field(min_length=1, max_length=5)


class ProspectRoutingBatchCreateResponse(BaseModel):
    batch_id: UUID
    status: str
    reused: bool
    processing_started: bool = False


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    clean = value.strip()
    return clean or None
