"""Opportunity application workflow: Company facts → scored judgment.

Consumes CompanyIngested / CompanyFactsChanged (application facts, no bus
yet) and orchestrates — it never computes a score itself (ADR-0020/0021):

    event → load Company → build OpportunityScoringInput
          → OpportunityScoringService.assess (replaceable; explainable MVP)
          → create Opportunity | append assessment (history append-only)
          → peek pending events → commit → drain AFTER success

Idempotency (two layers):
1. application: the persisted SHA-256 assessment fingerprint is compared
   against the whole history — replayed events SKIP before any write;
2. database: unique (opportunity_id, assessment_fingerprint); a race
   surfaces as DuplicateOperation from UoW.commit and becomes SKIPPED.

Event ordering rule (L9): events are peeked before commit but drained
only after a successful commit — a failed commit keeps them pending, so
retries publish exactly once and nothing external is called pre-commit.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.company import Company
from app.domain.events import CompanyFactsChanged, CompanyIngested
from app.domain.exceptions import DuplicateOperation
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
    qualification_decision: str | None = None
    data_completeness: float | None = None
    recommended_action: str | None = None
    scoring_version: str | None = None
    policy_version: str | None = None
    reasons: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    emitted_events_count: int = 0


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

            assessment = await self._scoring.assess(self._build_input(company, user_lens_version))
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
            elif opportunity.stage in CLOSED_STAGES:
                return OpportunityProcessingOutcome(
                    action=OpportunityProcessingAction.SKIPPED,
                    company_id=company.id,
                    opportunity_id=opportunity.id,
                    notes=(
                        f"opportunity is {opportunity.stage.value} — this event does not reopen",
                    ),
                )
            elif any(
                recorded.assessment_fingerprint == assessment.assessment_fingerprint
                for recorded in opportunity.history
            ):
                return OpportunityProcessingOutcome(
                    action=OpportunityProcessingAction.SKIPPED,
                    company_id=company.id,
                    opportunity_id=opportunity.id,
                    score=opportunity.score.value if opportunity.score else None,
                    confidence=opportunity.confidence.value if opportunity.confidence else None,
                    qualification_decision=(
                        opportunity.history[-1].qualification_decision.value
                        if opportunity.history[-1].qualification_decision
                        else None
                    ),
                    data_completeness=(
                        opportunity.history[-1].data_completeness.value
                        if opportunity.history[-1].data_completeness
                        else None
                    ),
                    recommended_action=opportunity.history[-1].recommended_action,
                    scoring_version=opportunity.history[-1].scoring_version,
                    policy_version=opportunity.history[-1].policy_version,
                    reasons=opportunity.history[-1].reasons,
                    notes=("identical assessment fingerprint already recorded — idempotent skip",),
                )
            else:
                opportunity.apply_assessment(assessment)
                await uow.opportunities.save(opportunity)
                action = OpportunityProcessingAction.REASSESSED

            # peek → commit → drain: events are published-after-commit facts
            pending_count = len(opportunity.pending_events)
            try:
                await uow.commit()
            except DuplicateOperation as exc:
                # unique (opportunity_id, fingerprint) race — someone else won;
                # pending events stay undrained on the discarded aggregate
                return OpportunityProcessingOutcome(
                    action=OpportunityProcessingAction.SKIPPED,
                    company_id=company.id,
                    opportunity_id=opportunity.id,
                    notes=(f"concurrent duplicate rejected by the database: {exc}",),
                )
            events = opportunity.drain_events()
            assert len(events) == pending_count

            return OpportunityProcessingOutcome(
                action=action,
                company_id=company.id,
                opportunity_id=opportunity.id,
                score=assessment.new_score.value,
                confidence=assessment.confidence.value,
                qualification_decision=(
                    assessment.qualification_decision.value
                    if assessment.qualification_decision
                    else None
                ),
                data_completeness=(
                    assessment.data_completeness.value if assessment.data_completeness else None
                ),
                recommended_action=assessment.recommended_action,
                scoring_version=assessment.scoring_version,
                policy_version=assessment.policy_version,
                reasons=assessment.reasons,
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
        if assessment.qualification_decision is None:
            return "missing qualification_decision"
        if assessment.data_completeness is None:
            return "missing data_completeness"
        if assessment.score_breakdown is None:
            return "missing score_breakdown"
        return None
