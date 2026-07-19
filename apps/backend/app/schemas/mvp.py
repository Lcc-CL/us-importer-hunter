"""Typed HTTP contracts for the minimal MVP prospect API."""

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.domain.services import SenderProfile
from app.domain.values import DimensionStatus, OpportunityAssessment, SourceReference
from app.workflows.mvp_prospect_analysis import (
    DraftApprovalOutcome,
    MvpProspectAnalysisCommand,
    MvpProspectAnalysisOutcome,
    OverallStatus,
    ProspectCompanyInput,
    ProspectContactInput,
    ProspectQueryResult,
    ProspectSignalInput,
    ProspectSourceInput,
    StageStatus,
)

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ApproverName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class ProspectSignalRequest(BaseModel):
    kind: NonBlank
    detail: NonBlank


class ProspectSourceRequest(BaseModel):
    source: NonBlank
    reference: NonBlank
    retrieved_at: datetime | None = None


class ProspectCompanyRequest(BaseModel):
    name: NonBlank
    website: NonBlank | None = None
    sources: list[ProspectSourceRequest] = Field(default_factory=list)
    source: NonBlank | None = None
    signals: list[ProspectSignalRequest] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_real_source_reference(self) -> Self:
        if not self.sources and self.source is None:
            raise ValueError("company.sources requires at least one real source reference")
        if self.source is not None and self.website is None:
            raise ValueError(
                "legacy company.source requires company.website; migrate to "
                "company.sources with an explicit reference"
            )
        return self


class ProspectContactRequest(BaseModel):
    name: NonBlank
    source: NonBlank
    title: NonBlank | None = None
    email: NonBlank | None = None
    linkedin_url: NonBlank | None = None
    phone: NonBlank | None = None


class SenderRequest(BaseModel):
    name: NonBlank
    company: NonBlank
    value_proposition: NonBlank


class AnalysisOptionsRequest(BaseModel):
    generate_email: bool = True


class ProspectAnalysisRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "company": {
                        "name": "Pacific Home Goods Inc.",
                        "website": "https://pacifichomegoods.example",
                        "sources": [
                            {
                                "source": "importyeti",
                                "reference": "https://www.importyeti.com/company/pacific-home-goods",
                            },
                            {
                                "source": "company_website",
                                "reference": "https://pacifichomegoods.example/about",
                            },
                        ],
                        "signals": [
                            {"kind": "import_activity", "detail": "customs shipments recorded"},
                            {"kind": "china_dependency", "detail": "China origin observed"},
                            {"kind": "shipping_fit", "detail": "ocean FCL container freight"},
                            {"kind": "cargo_value", "detail": "high value cargo"},
                            {"kind": "company_scale", "detail": "warehouse and employees"},
                            {"kind": "growth", "detail": "growing import activity"},
                            {"kind": "complexity", "detail": "multi-origin logistics"},
                        ],
                    },
                    "contact": {
                        "name": "Maria Chen",
                        "title": "Director of Supply Chain",
                        "email": "maria@pacifichomegoods.example",
                        "linkedin_url": "https://www.linkedin.com/in/maria-chen",
                        "phone": "+1 415 555 0100",
                        "source": "company_website",
                    },
                    "sender": {
                        "name": "Alex Morgan",
                        "company": "Harbor Bridge Logistics",
                        "value_proposition": "We simplify Asia-to-US inbound freight.",
                    },
                    "options": {"generate_email": True},
                }
            ]
        }
    )

    company: ProspectCompanyRequest
    contact: ProspectContactRequest | None = None
    sender: SenderRequest
    options: AnalysisOptionsRequest = Field(default_factory=AnalysisOptionsRequest)

    def to_command(self, request_id: str) -> MvpProspectAnalysisCommand:
        return MvpProspectAnalysisCommand(
            request_id=request_id,
            company=ProspectCompanyInput(
                name=self.company.name,
                website=self.company.website,
                signals=tuple(
                    ProspectSignalInput(kind=signal.kind, detail=signal.detail)
                    for signal in self.company.signals
                ),
                sources=tuple(
                    ProspectSourceInput(
                        source=source.source,
                        reference=source.reference,
                        retrieved_at=source.retrieved_at,
                    )
                    for source in self.company.sources
                ),
                source=self.company.source,
            ),
            contact=(
                ProspectContactInput(
                    name=self.contact.name,
                    source=self.contact.source,
                    title=self.contact.title,
                    email=self.contact.email,
                    linkedin_url=self.contact.linkedin_url,
                    phone=self.contact.phone,
                )
                if self.contact is not None
                else None
            ),
            sender=SenderProfile(
                name=self.sender.name,
                company=self.sender.company,
                value_proposition=self.sender.value_proposition,
            ),
            generate_email=self.options.generate_email,
        )


class CompanyAnalysisResponse(BaseModel):
    action: StageStatus
    company_id: UUID | None = None
    name: str
    notes: list[str] = Field(default_factory=list)


class OpportunityAnalysisResponse(BaseModel):
    action: StageStatus
    opportunity_id: UUID | None = None
    score: float | None = None
    confidence: float | None = None
    data_completeness: float | None = None
    qualification_decision: str | None = None
    recommended_action: str | None = None
    reasons: list[str] = Field(default_factory=list)


class ContactAnalysisResponse(BaseModel):
    action: StageStatus
    contact_id: UUID | None = None
    notes: list[str] = Field(default_factory=list)


class DecisionMakerAnalysisResponse(BaseModel):
    action: StageStatus
    selected_contact_id: UUID | None = None
    recommended_channel: str | None = None
    confidence: float | None = None
    reasons: list[str] = Field(default_factory=list)


class EmailDraftAnalysisResponse(BaseModel):
    action: StageStatus
    outreach_id: UUID | None = None
    version: int | None = None
    subject: str | None = None
    body: str | None = None
    status: str | None = None
    notes: list[str] = Field(default_factory=list)


class ProspectAnalysisResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "request_id": "11111111-1111-1111-1111-111111111111",
                    "overall_status": "COMPLETED",
                    "company": {
                        "action": "CREATED",
                        "company_id": "22222222-2222-2222-2222-222222222222",
                        "name": "Pacific Home Goods Inc.",
                        "notes": [],
                    },
                    "opportunity": {
                        "action": "QUALIFIED",
                        "opportunity_id": "33333333-3333-3333-3333-333333333333",
                        "score": 75.5,
                        "confidence": 0.7,
                        "data_completeness": 1.0,
                        "qualification_decision": "qualified",
                        "recommended_action": "prepare_outreach",
                        "reasons": ["evidence-backed assessment"],
                    },
                    "contact": {
                        "action": "CREATED",
                        "contact_id": "44444444-4444-4444-4444-444444444444",
                        "notes": [],
                    },
                    "decision_maker": {
                        "action": "SELECTED",
                        "selected_contact_id": "44444444-4444-4444-4444-444444444444",
                        "recommended_channel": "email",
                        "confidence": 0.9,
                        "reasons": ["supply-chain director with reachable email"],
                    },
                    "email_draft": {
                        "action": "GENERATED",
                        "outreach_id": "55555555-5555-5555-5555-555555555555",
                        "version": 1,
                        "subject": "Freight partnership for Pacific Home Goods",
                        "body": "Hi Maria, ...",
                        "status": "generated",
                        "notes": ["draft awaits human review"],
                    },
                    "warnings": [],
                    "created_at": "2026-07-16T12:00:00Z",
                }
            ]
        }
    )

    request_id: str
    overall_status: OverallStatus
    company: CompanyAnalysisResponse
    opportunity: OpportunityAnalysisResponse
    contact: ContactAnalysisResponse
    decision_maker: DecisionMakerAnalysisResponse
    email_draft: EmailDraftAnalysisResponse
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime

    @classmethod
    def from_outcome(cls, outcome: MvpProspectAnalysisOutcome) -> Self:
        return cls(
            request_id=outcome.request_id,
            overall_status=outcome.overall_status,
            company=CompanyAnalysisResponse(
                action=outcome.company.action,
                company_id=outcome.company.company_id,
                name=outcome.company.name,
                notes=list(outcome.company.notes),
            ),
            opportunity=OpportunityAnalysisResponse(
                action=outcome.opportunity.action,
                opportunity_id=outcome.opportunity.opportunity_id,
                score=outcome.opportunity.score,
                confidence=outcome.opportunity.confidence,
                data_completeness=outcome.opportunity.data_completeness,
                qualification_decision=outcome.opportunity.qualification_decision,
                recommended_action=outcome.opportunity.recommended_action,
                reasons=list(outcome.opportunity.reasons),
            ),
            contact=ContactAnalysisResponse(
                action=outcome.contact.action,
                contact_id=outcome.contact.contact_id,
                notes=list(outcome.contact.notes),
            ),
            decision_maker=DecisionMakerAnalysisResponse(
                action=outcome.decision_maker.action,
                selected_contact_id=outcome.decision_maker.selected_contact_id,
                recommended_channel=outcome.decision_maker.recommended_channel,
                confidence=outcome.decision_maker.confidence,
                reasons=list(outcome.decision_maker.reasons),
            ),
            email_draft=EmailDraftAnalysisResponse(
                action=outcome.email_draft.action,
                outreach_id=outcome.email_draft.outreach_id,
                version=outcome.email_draft.version,
                subject=outcome.email_draft.subject,
                body=outcome.email_draft.body,
                status=outcome.email_draft.status,
                notes=list(outcome.email_draft.notes),
            ),
            warnings=list(outcome.warnings),
            created_at=outcome.created_at,
        )


class CompanySourceSummaryResponse(BaseModel):
    """One distinct source name, and how many references carry it.

    The stored `company_sources` rows are the audit record and keep every
    reference: two pages of the same site are two rows, correctly. This
    summary is for display, so it collapses them by name — and reports the
    count rather than silently hiding that there were several.
    """

    source: str
    reference_count: int


class CompanyDetailResponse(BaseModel):
    company_id: UUID
    name: str
    website: str | None
    verified: bool
    #: Distinct source names in first-seen order, with their reference counts.
    #: Deduplicated here rather than in the UI so every consumer gets a list
    #: that is safe to key on; the audit rows are untouched.
    sources: list[CompanySourceSummaryResponse]
    signals: list[str]


#: Dimensions a company website structurally cannot prove. Missing them is a
#: gap in the *source*, not a verdict on the company — the UI must say so, or
#: a reviewer reads REVIEW as "weak prospect" and drops a good one.
IMPORT_EVIDENCE_DIMENSIONS = frozenset(
    {"import_activity", "china_dependency", "cargo_value_potential"}
)

#: Not a qualification decision. It names the next action when the only thing
#: standing between this company and a verdict is customs-grade evidence.
IMPORT_EVIDENCE_REQUIRED = "IMPORT_EVIDENCE_REQUIRED"


class DimensionExplanationResponse(BaseModel):
    """One dimension, explained: what it contributed and why."""

    dimension: str
    status: str
    weight: float
    earned_score: float
    #: Share of the total score this dimension actually contributed.
    score_contribution: float
    evidence_status: str
    unknown_reason: str | None
    needs_import_evidence: bool
    reasons: list[str]


class QualificationExplanationResponse(BaseModel):
    """Why the verdict is what it is, without restating the verdict.

    Derived from the stored breakdown — no weight, threshold or persisted
    assessment is changed to produce it.
    """

    dimensions: list[DimensionExplanationResponse]
    evidence_obtained: list[str]
    missing_key_evidence: list[str]
    #: Dimensions blocked on customs-grade data rather than on the company.
    import_evidence_missing: list[str]
    #: Score that is unreachable from a company website alone.
    unreachable_weight: float
    hard_gate_hits: list[str]
    #: Suggested next step. Never a qualification decision.
    next_action: str | None


class AssessmentDetailResponse(BaseModel):
    opportunity_id: UUID
    score: float
    confidence: float
    data_completeness: float | None
    qualification_decision: str | None
    recommended_action: str | None
    reasons: list[str]
    scoring_version: str
    policy_version: str
    assessed_at: datetime
    explanation: QualificationExplanationResponse | None = None


class ContactChannelResponse(BaseModel):
    type: str
    value: str
    verification_status: str


class ContactDetailResponse(BaseModel):
    contact_id: UUID
    name: str
    title: str | None
    department: str
    seniority: str
    status: str
    channels: list[ContactChannelResponse]


class DecisionMakerRankingResponse(BaseModel):
    contact_id: UUID
    total_score: float
    confidence: float
    recommended_channel: str | None
    reasons: list[str]


class DecisionMakerDetailResponse(BaseModel):
    selected_contact_id: UUID | None
    rankings: list[DecisionMakerRankingResponse]


class EmailDraftDetailResponse(BaseModel):
    outreach_id: UUID
    version: int
    subject: str
    body: str
    status: str = Field(deprecated=True)
    approval_status: str
    approved_at: datetime | None
    approved_by_name: str | None
    provider: str
    model: str
    prompt_version: str
    generated_at: datetime


class EmailDraftSummaryResponse(BaseModel):
    outreach_id: UUID
    version: int
    subject: str
    status: str = Field(deprecated=True)
    approval_status: str
    approved_at: datetime | None
    approved_by_name: str | None
    generated_at: datetime


class ProspectDetailResponse(BaseModel):
    company: CompanyDetailResponse
    latest_assessment: AssessmentDetailResponse | None
    qualification_decision: str | None
    contacts: list[ContactDetailResponse]
    decision_maker: DecisionMakerDetailResponse
    latest_email_draft: EmailDraftDetailResponse | None
    draft_history: list[EmailDraftSummaryResponse]

    @classmethod
    def from_result(cls, result: ProspectQueryResult) -> Self:
        company = result.company
        assessment = (
            result.opportunity.history[-1]
            if result.opportunity is not None and result.opportunity.history
            else None
        )
        all_drafts = sorted(
            (
                (outreach, draft)
                for outreach in result.outreaches
                for draft in outreach.drafts
            ),
            key=lambda item: item[1].generated_at,
            reverse=True,
        )
        latest = all_drafts[0] if all_drafts else None
        selected_contact_id = latest[0].contact_id if latest is not None else None
        return cls(
            company=CompanyDetailResponse(
                company_id=company.id,
                name=company.name.value,
                website=company.website.value if company.website else None,
                verified=company.verified,
                sources=_summarize_sources(company.sources),
                signals=list(company.signals),
            ),
            latest_assessment=(
                AssessmentDetailResponse(
                    opportunity_id=result.opportunity.id,
                    score=assessment.new_score.value,
                    confidence=assessment.confidence.value,
                    data_completeness=(
                        assessment.data_completeness.value
                        if assessment.data_completeness
                        else None
                    ),
                    qualification_decision=(
                        assessment.qualification_decision.value
                        if assessment.qualification_decision
                        else None
                    ),
                    recommended_action=assessment.recommended_action,
                    reasons=list(assessment.reasons),
                    scoring_version=assessment.scoring_version,
                    policy_version=assessment.policy_version,
                    explanation=_explain(assessment),
                    assessed_at=assessment.assessed_at,
                )
                if result.opportunity is not None and assessment is not None
                else None
            ),
            qualification_decision=(
                assessment.qualification_decision.value
                if assessment is not None and assessment.qualification_decision
                else None
            ),
            contacts=[
                ContactDetailResponse(
                    contact_id=contact.id,
                    name=contact.name.value,
                    title=contact.title.raw if contact.title else None,
                    department=contact.department.value,
                    seniority=contact.seniority.value,
                    status=contact.status.value,
                    channels=[
                        ContactChannelResponse(
                            type=channel.channel_type.value,
                            value=channel.display_value,
                            verification_status=channel.verification_status.value,
                        )
                        for channel in contact.usable_channels
                    ],
                )
                for contact in result.contacts
            ],
            decision_maker=DecisionMakerDetailResponse(
                selected_contact_id=selected_contact_id,
                rankings=[
                    DecisionMakerRankingResponse(
                        contact_id=item.contact_id,
                        total_score=item.total_score,
                        confidence=item.confidence.value,
                        recommended_channel=(
                            item.recommended_channel.value if item.recommended_channel else None
                        ),
                        reasons=list(item.reasons),
                    )
                    for item in result.decision_maker_rankings
                ],
            ),
            latest_email_draft=(
                EmailDraftDetailResponse(
                    outreach_id=latest[0].id,
                    version=latest[1].version,
                    subject=latest[1].subject,
                    body=latest[1].body,
                    status=latest[1].status.value,
                    approval_status=latest[1].approval_status.value,
                    approved_at=latest[1].approved_at,
                    approved_by_name=latest[1].approved_by_name,
                    provider=latest[1].provider,
                    model=latest[1].model,
                    prompt_version=latest[1].prompt_version,
                    generated_at=latest[1].generated_at,
                )
                if latest is not None
                else None
            ),
            draft_history=[
                EmailDraftSummaryResponse(
                    outreach_id=outreach.id,
                    version=draft.version,
                    subject=draft.subject,
                    status=draft.status.value,
                    approval_status=draft.approval_status.value,
                    approved_at=draft.approved_at,
                    approved_by_name=draft.approved_by_name,
                    generated_at=draft.generated_at,
                )
                for outreach, draft in all_drafts
            ],
        )


class DraftApprovalRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"approver_name": "Alex Morgan"}]}
    )

    approver_id: UUID | None = None
    approver_name: ApproverName | None = None

    @model_validator(mode="after")
    def require_approver(self) -> Self:
        if self.approver_id is None and self.approver_name is None:
            raise ValueError("approver_id or approver_name is required")
        return self


class DraftApprovalResponse(BaseModel):
    outreach_id: UUID
    version: int
    status: str = Field(deprecated=True)
    approval_status: str
    approved_at: datetime
    approved_by: str = Field(deprecated=True)
    approved_by_name: str

    @classmethod
    def from_outcome(cls, outcome: DraftApprovalOutcome) -> Self:
        return cls(
            outreach_id=outcome.outreach_id,
            version=outcome.version,
            status=outcome.status,
            approval_status=outcome.approval_status,
            approved_at=outcome.approved_at,
            approved_by=outcome.approved_by,
            approved_by_name=outcome.approved_by_name,
        )


class ApiErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str


def _explain(assessment: OpportunityAssessment) -> QualificationExplanationResponse | None:
    """Turn a stored breakdown into something a salesperson can act on.

    Read-only by construction: it reports what the scorer already decided and
    changes no weight, threshold or persisted row.
    """
    breakdown = assessment.score_breakdown
    if breakdown is None:
        return None

    total = assessment.new_score.value or 0.0
    dimensions: list[DimensionExplanationResponse] = []
    obtained: list[str] = []
    missing: list[str] = []
    import_missing: list[str] = []
    unreachable = 0.0

    for item in breakdown.dimensions:
        name = item.dimension.value
        assessed = item.status is DimensionStatus.ASSESSED
        needs_import = not assessed and name in IMPORT_EVIDENCE_DIMENSIONS
        if assessed:
            obtained.append(name)
        else:
            missing.append(name)
        if needs_import:
            import_missing.append(name)
            unreachable += item.weight

        dimensions.append(
            DimensionExplanationResponse(
                dimension=name,
                status=item.status.value,
                weight=item.weight,
                earned_score=item.earned_score,
                score_contribution=(
                    round(item.earned_score / total, 4) if total > 0 else 0.0
                ),
                evidence_status=("present" if assessed else "absent"),
                unknown_reason=(None if assessed else item.status.value),
                needs_import_evidence=needs_import,
                reasons=list(item.reasons),
            )
        )

    hard_gates = [hit for hit in getattr(breakdown, "hard_gate_hits", ()) or ()]
    next_action = IMPORT_EVIDENCE_REQUIRED if import_missing else None

    return QualificationExplanationResponse(
        dimensions=dimensions,
        evidence_obtained=obtained,
        missing_key_evidence=missing,
        import_evidence_missing=import_missing,
        unreachable_weight=round(unreachable, 2),
        hard_gate_hits=[str(hit) for hit in hard_gates],
        next_action=next_action,
    )


def _summarize_sources(
    sources: "Sequence[SourceReference]",
) -> list[CompanySourceSummaryResponse]:
    """Collapse references by source name, preserving first-seen order.

    Two references to the same site are two audit rows and stay that way in
    the database. For display they are one source seen twice — which is what
    the count says, instead of rendering the same name twice and leaving the
    UI to key on a value that is not unique.
    """
    counts: dict[str, int] = {}
    for reference in sources:
        name = reference.source.strip()
        counts[name] = counts.get(name, 0) + 1
    return [
        CompanySourceSummaryResponse(source=name, reference_count=count)
        for name, count in counts.items()
    ]
