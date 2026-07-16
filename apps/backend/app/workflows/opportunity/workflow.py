"""Opportunity application workflow: Company facts → scored judgment.

Consumes CompanyIngested / CompanyFactsChanged (application facts, no bus
yet) and orchestrates — it never computes a score itself (ADR-0020):

    event → load Company → build OpportunityScoringInput
          → OpportunityScoringService.assess (replaceable; deterministic MVP)
          → create Opportunity | append assessment (history append-only)
          → one UnitOfWork, explicit commit
          → typed OpportunityProcessingOutcome

Idempotency: an assessment fingerprint (scoring_version + score +
confidence + reasons + evidence claims) is compared against the latest
history entry — replaying the same event over unchanged facts SKIPs
instead of appending a duplicate or re-emitting events.

Business non-conditions return outcomes, never exceptions: unknown
company (REJECTED), no sources (SKIPPED), incomplete assessment
(REJECTED), duplicate fingerprint (SKIPPED), closed opportunity
(SKIPPED). Scorer crashes propagate — the UoW context rolls back.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.company import Company
from app.domain.events import CompanyFactsChanged, CompanyIngested
from app.domain.opportunity import CLOSED_STAGES, Opportunity
from app.domain.repositories import UnitOfWork
from app.domain.services import OpportunityScoringInput, OpportunityScoringService
from app.domain.values import OpportunityAssessment


class OpportunityProcessingAction(StrEnum):
    CREATED = "created"
    REASSESSED = "reassessed"
    SKIPPED = "skipped"
    REJECTED = "rejected"


@dataclass(frozen=True)
class OpportunityProcessingOutcome:
    action: OpportunityProcessingAction
    company_id: UUID
    opportunity_id: UUID | None = None
    score: float | None = None
    confidence: float | None = None
    notes: tuple[str, ...] = ()
    emitted_events_count: int = 0


def _fingerprint(assessment: OpportunityAssessment) -> tuple[object, ...]:
    """What makes two assessments 'the same judgment': same algorithm
    over the same facts yields identical score/confidence/reasons/claims."""
    return (
        assessment.scoring_version,
        assessment.new_score,
        assessment.confidence,
        assessment.reasons,
        tuple(evidence.claim for evidence in assessment.evidence),
    )


class OpportunityApplicationWorkflow:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        scoring_service: OpportunityScoringService,
    ) -> None:
        self._uow_factory = uow_factory
        self._scoring = scoring_service

    async def handle(
        self,
        event: CompanyIngested | CompanyFactsChanged,
        *,
        user_id: UUID,
        user_lens_version: str | None = None,
    ) -> OpportunityProcessingOutcome:
        async with self._uow_factory() as uow:
            company = await uow.companies.get_by_id(event.company_id)
            if company is None:
                return OpportunityProcessingOutcome(
                    action=OpportunityProcessingAction.REJECTED,
                    company_id=event.company_id,
                    notes=("company not found — nothing to assess",),
                )
            if not company.sources:
                return OpportunityProcessingOutcome(
                    action=OpportunityProcessingAction.SKIPPED,
                    company_id=company.id,
                    notes=("company has no source references — nothing trustworthy to score",),
                )

            assessment = await self._scoring.assess(
                self._build_input(company, user_lens_version)
            )
            incomplete = self._incompleteness(assessment)
            if incomplete:
                return OpportunityProcessingOutcome(
                    action=OpportunityProcessingAction.REJECTED,
                    company_id=company.id,
                    notes=(f"scoring service returned an incomplete assessment: {incomplete}",),
                )

            opportunity = await uow.opportunities.get_for_company_and_user(company.id, user_id)

            if opportunity is None:
                opportunity = Opportunity.create_for_company(company.id, user_id)
                opportunity.apply_assessment(assessment)
                await uow.opportunities.add(opportunity)
                action = OpportunityProcessingAction.CREATED
                notes: tuple[str, ...] = ()
            elif opportunity.stage in CLOSED_STAGES:
                return OpportunityProcessingOutcome(
                    action=OpportunityProcessingAction.SKIPPED,
                    company_id=company.id,
                    opportunity_id=opportunity.id,
                    notes=(
                        f"opportunity is {opportunity.stage.value} — this event does not reopen",
                    ),
                )
            elif opportunity.history and _fingerprint(opportunity.history[-1]) == _fingerprint(
                assessment
            ):
                return OpportunityProcessingOutcome(
                    action=OpportunityProcessingAction.SKIPPED,
                    company_id=company.id,
                    opportunity_id=opportunity.id,
                    score=opportunity.score.value if opportunity.score else None,
                    confidence=opportunity.confidence.value if opportunity.confidence else None,
                    notes=("identical assessment already recorded — idempotent skip",),
                )
            else:
                opportunity.apply_assessment(assessment)
                await uow.opportunities.save(opportunity)
                action = OpportunityProcessingAction.REASSESSED
                notes = ()

            events = opportunity.drain_events()
            await uow.commit()
            return OpportunityProcessingOutcome(
                action=action,
                company_id=company.id,
                opportunity_id=opportunity.id,
                score=assessment.new_score.value,
                confidence=assessment.confidence.value,
                notes=notes,
                emitted_events_count=len(events),
            )

    def _build_input(
        self, company: Company, user_lens_version: str | None
    ) -> OpportunityScoringInput:
        return OpportunityScoringInput(
            company_id=company.id,
            company_name=company.name.value,
            website_host=company.website.host if company.website else None,
            verified=company.verified,
            signals=company.signals,
            sources=company.sources,
            scoring_version=self._scoring.scoring_version,
            user_lens_version=user_lens_version,
        )

    @staticmethod
    def _incompleteness(assessment: OpportunityAssessment) -> str | None:
        if assessment.priority is None:
            return "missing priority"
        if not (assessment.recommended_action or "").strip():
            return "missing recommended_action"
        if not (assessment.assessed_by or "").strip():
            return "missing assessed_by"
        return None
