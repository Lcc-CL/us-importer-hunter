"""Typed HTTP contracts for the internal research API.

What a response may carry is a security decision, not a convenience one.
Deliberately absent: credentials, base URLs, system prompts, raw HTML and full
page text. Only page metadata and the short snippets cited as evidence leave
the server (ADR-0026 §5).
"""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.domain.research import ResearchRun
from app.workflows.research import ResearchOutcome, ReviewOutcome

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ResearchRunRequest(BaseModel):
    """Either an existing company, or a prospect that is not in the database.

    A. `company_id` given — the name snapshot is read from the database and
       `website` defaults to the company's own website.
    B. `company_id` absent — `company_name` and `website` are both required.
       No Company is created.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"company_id": "7e1a93a8-84bb-49b1-857a-22d2852f4fb5"},
                {
                    "company_name": "Acme Hardware",
                    "website": "https://acme-hardware.example",
                },
            ]
        }
    )

    company_id: UUID | None = None
    company_name: NonBlank | None = None
    website: NonBlank | None = None

    @model_validator(mode="after")
    def require_identity(self) -> Self:
        if self.company_id is None:
            if self.company_name is None:
                raise ValueError("company_name is required when company_id is not given")
            if self.website is None:
                raise ValueError("website is required when company_id is not given")
        return self


class ResearchPageResponse(BaseModel):
    """Metadata only — never the page body."""

    position: int
    url: str
    final_url: str
    http_status: int
    content_type: str
    fetched_at: datetime
    content_chars: int
    truncated: bool
    discovery_reason: str


class ResearchClaimResponse(BaseModel):
    position: int
    kind: str
    detail: str
    evidence_snippet: str
    source_url: str
    confidence: float


class RejectedClaimResponse(BaseModel):
    """Why a proposal was refused — kept visible so extractor quality is
    measurable instead of silently disappearing."""

    reason: str
    kind: str
    detail: str
    warning: str


class ResearchProfileResponse(BaseModel):
    summary: str | None = None
    industry: str | None = None
    products: list[str] = []
    locations: list[str] = []
    size_hint: str | None = None
    year_founded: str | None = None
    mentions_importing: bool | None = None


class ExtractorResponse(BaseModel):
    """Which extractor produced this — provider, model and prompt version
    only. No key, no endpoint."""

    provider: str
    model: str
    prompt_version: str


class ResearchRunResponse(BaseModel):
    research_id: UUID
    company_id: UUID | None
    company_name: str
    website: str
    status: str
    failure_code: str | None
    started_at: datetime
    completed_at: datetime | None
    pages_fetched: int
    pages_failed: int
    claims_extracted: int
    claims_validated: int
    extractor: ExtractorResponse | None
    profile: ResearchProfileResponse
    pages: list[ResearchPageResponse]
    claims: list[ResearchClaimResponse]
    rejected_claims: list[RejectedClaimResponse]
    warnings: list[str]

    @classmethod
    def from_run(cls, run: ResearchRun) -> "ResearchRunResponse":
        by_position = {page.position: page for page in run.pages}
        return cls(
            research_id=run.id,
            company_id=run.company_id,
            company_name=run.company_name,
            website=run.website,
            status=run.status.value,
            failure_code=run.failure_code.value if run.failure_code else None,
            started_at=run.started_at,
            completed_at=run.completed_at,
            pages_fetched=run.pages_fetched,
            pages_failed=run.pages_failed,
            claims_extracted=run.claims_extracted,
            claims_validated=run.claims_validated,
            extractor=(
                ExtractorResponse(
                    provider=run.extractor.provider,
                    model=run.extractor.model,
                    prompt_version=run.extractor.prompt_version,
                )
                if run.extractor
                else None
            ),
            profile=ResearchProfileResponse(
                summary=run.profile.summary,
                industry=run.profile.industry,
                products=list(run.profile.products),
                locations=list(run.profile.locations),
                size_hint=run.profile.size_hint,
                year_founded=run.profile.year_founded,
                mentions_importing=run.profile.mentions_importing,
            ),
            pages=[
                ResearchPageResponse(
                    position=page.position,
                    url=page.url,
                    final_url=page.final_url,
                    http_status=page.http_status,
                    content_type=page.content_type,
                    fetched_at=page.fetched_at,
                    content_chars=page.content_chars,
                    truncated=page.truncated,
                    discovery_reason=page.discovery_reason,
                )
                for page in run.pages
            ],
            claims=[
                ResearchClaimResponse(
                    position=claim.position,
                    kind=claim.kind,
                    detail=claim.detail,
                    evidence_snippet=claim.evidence_snippet,
                    source_url=(
                        by_position[claim.source_page_position].url
                        if claim.source_page_position in by_position
                        else ""
                    ),
                    confidence=claim.confidence,
                )
                for claim in run.claims
            ],
            rejected_claims=[
                RejectedClaimResponse(
                    reason=rejection.reason.value,
                    kind=rejection.kind,
                    detail=rejection.detail,
                    warning=rejection.warning,
                )
                for rejection in run.rejected_claims
            ],
            warnings=list(run.warnings),
        )


class ResearchRunSummaryResponse(BaseModel):
    """One row of a company's research history."""

    research_id: UUID
    website: str
    status: str
    failure_code: str | None
    started_at: datetime
    completed_at: datetime | None
    pages_fetched: int
    claims_validated: int

    @classmethod
    def from_run(cls, run: ResearchRun) -> "ResearchRunSummaryResponse":
        return cls(
            research_id=run.id,
            website=run.website,
            status=run.status.value,
            failure_code=run.failure_code.value if run.failure_code else None,
            started_at=run.started_at,
            completed_at=run.completed_at,
            pages_fetched=run.pages_fetched,
            claims_validated=run.claims_validated,
        )


class ResearchRunListResponse(BaseModel):
    company_id: UUID
    runs: list[ResearchRunSummaryResponse]


class ResearchRunCreatedResponse(ResearchRunResponse):
    """201 body. `action` mirrors the workflow outcome so a caller can branch
    without re-deriving it from status."""

    action: str

    @classmethod
    def from_outcome(
        cls, outcome: ResearchOutcome, run: ResearchRun
    ) -> "ResearchRunCreatedResponse":
        base = ResearchRunResponse.from_run(run)
        return cls(**base.model_dump(), action=outcome.action.value)


# --- claim review / promotion (phase 3.3) ---------------------------------


class ClaimDecisionRequest(BaseModel):
    """One verdict. `edited_detail` / `edited_kind` are only valid for edited."""

    claim_position: int
    decision: Literal["accepted", "edited", "rejected"]
    edited_detail: NonBlank | None = None
    edited_kind: NonBlank | None = None

    @model_validator(mode="after")
    def edits_only_for_edited(self) -> Self:
        if self.decision == "edited":
            if self.edited_detail is None:
                raise ValueError("an edited decision requires edited_detail")
        elif self.edited_detail is not None or self.edited_kind is not None:
            raise ValueError("edited_detail/edited_kind are only valid for an edited decision")
        return self


class ConfirmResearchRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "reviewer_name": "Lcc",
                    "decisions": [
                        {"claim_position": 0, "decision": "accepted"},
                        {
                            "claim_position": 1,
                            "decision": "edited",
                            "edited_detail": "改写后的描述",
                            "edited_kind": "shipping_fit",
                        },
                        {"claim_position": 2, "decision": "rejected"},
                    ],
                }
            ]
        }
    )

    reviewer_name: NonBlank
    target_company_id: UUID | None = None
    decisions: list[ClaimDecisionRequest]

    @model_validator(mode="after")
    def require_decisions(self) -> Self:
        if not self.decisions:
            raise ValueError("at least one decision is required")
        positions = [decision.claim_position for decision in self.decisions]
        if len(positions) != len(set(positions)):
            raise ValueError("each claim may appear at most once per request")
        return self


class PromotionResultResponse(BaseModel):
    claim_position: int
    decision: str
    kind: str
    detail: str
    company_source_position: int | None
    company_signal_position: int | None
    source_reused: bool
    idempotent: bool


class ProspectFormPayloadResponse(BaseModel):
    """Returned when there is no company to write to: phase 4 fills the
    existing prospect form with this and submits it unchanged."""

    company_name: str
    website: str
    sources: list[dict[str, str]]
    signals: list[dict[str, str]]


class ReviewSummaryResponse(BaseModel):
    accepted: int
    edited: int
    rejected: int
    total: int


class ConfirmResearchResponse(BaseModel):
    research_id: UUID
    action: str
    company_id: UUID | None
    summary: ReviewSummaryResponse
    promotions: list[PromotionResultResponse]
    application_payload: ProspectFormPayloadResponse | None
    warnings: list[str]

    @classmethod
    def from_outcome(cls, outcome: ReviewOutcome) -> "ConfirmResearchResponse":
        payload = outcome.application_payload
        return cls(
            research_id=outcome.research_id,
            action=outcome.action.value,
            company_id=outcome.company_id,
            summary=ReviewSummaryResponse(
                accepted=outcome.accepted,
                edited=outcome.edited,
                rejected=outcome.rejected,
                total=len(outcome.results),
            ),
            promotions=[
                PromotionResultResponse(
                    claim_position=result.claim_position,
                    decision=result.decision.value,
                    kind=result.kind,
                    detail=result.detail,
                    company_source_position=result.company_source_position,
                    company_signal_position=result.company_signal_position,
                    source_reused=result.source_reused,
                    idempotent=result.idempotent,
                )
                for result in outcome.results
            ],
            application_payload=(
                ProspectFormPayloadResponse(
                    company_name=payload.company_name,
                    website=payload.website,
                    sources=[dict(item) for item in payload.sources],
                    signals=[dict(item) for item in payload.signals],
                )
                if payload
                else None
            ),
            warnings=list(outcome.warnings),
        )
