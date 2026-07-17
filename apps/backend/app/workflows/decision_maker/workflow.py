"""Decision-maker selection workflow: who should the email go to?

    (company_id, opportunity_id)
      → load eligible contacts (not INVALID / INACTIVE)
      → DecisionMakerSelectionService.rank (versioned policy)
      → persist fit assessments (append-only; duplicate fingerprints noted)
      → SELECTED | REVIEW | RESEARCH_MORE
      → DecisionMakerSelected event in the outcome for the email-draft
        workflow (next lesson) — this workflow never creates drafts.

Selection thresholds are workflow-level routing (analogous to L9's
qualification): they decide the next process step, not a business score.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.contact import ContactStatus, DecisionMakerFitAssessment, SelectionThresholds
from app.domain.events import DecisionMakerSelected
from app.domain.exceptions import DuplicateOperation
from app.domain.repositories import UnitOfWork
from app.domain.services import DecisionMakerSelectionService


class DecisionMakerSelectionAction(StrEnum):
    SELECTED = "selected"
    REVIEW = "review"
    RESEARCH_MORE = "research_more"
    REJECTED = "rejected"


@dataclass(frozen=True)
class DecisionMakerSelectionOutcome:
    action: DecisionMakerSelectionAction
    company_id: UUID
    opportunity_id: UUID
    selected_contact_id: UUID | None = None
    ranked_candidates: tuple[DecisionMakerFitAssessment, ...] = ()
    recommended_channel: str | None = None
    confidence: float | None = None
    reasons: tuple[str, ...] = ()
    policy_version: str = ""
    event: DecisionMakerSelected | None = None


class DecisionMakerSelectionWorkflow:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        selection_service: DecisionMakerSelectionService,
        thresholds: SelectionThresholds | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._selection = selection_service
        self._thresholds = thresholds or SelectionThresholds()

    async def handle(
        self, *, company_id: UUID, opportunity_id: UUID
    ) -> DecisionMakerSelectionOutcome:
        policy = self._selection.policy_version
        async with self._uow_factory() as uow:
            contacts = [
                contact
                for contact in await uow.contacts.list_for_company(company_id)
                if contact.status not in (ContactStatus.INVALID, ContactStatus.INACTIVE)
            ]
            if not contacts:
                return DecisionMakerSelectionOutcome(
                    action=DecisionMakerSelectionAction.RESEARCH_MORE,
                    company_id=company_id,
                    opportunity_id=opportunity_id,
                    reasons=("no eligible contacts at this company — find people first",),
                    policy_version=policy,
                )

            ranked = await self._selection.rank(contacts)
            notes: list[str] = []
            for assessment in ranked:
                try:
                    await uow.contacts.record_fit_assessment(assessment)
                except DuplicateOperation:
                    notes.append(
                        f"assessment for {assessment.contact_id} already recorded — skipped"
                    )
            try:
                await uow.commit()
            except DuplicateOperation:
                notes.append(
                    "concurrent duplicate assessment rejected — reused current ranking"
                )

            best = ranked[0]
            if (
                best.total_score >= self._thresholds.select_score
                and best.confidence.value >= self._thresholds.min_confidence
            ):
                return DecisionMakerSelectionOutcome(
                    action=DecisionMakerSelectionAction.SELECTED,
                    company_id=company_id,
                    opportunity_id=opportunity_id,
                    selected_contact_id=best.contact_id,
                    ranked_candidates=ranked,
                    recommended_channel=(
                        best.recommended_channel.value if best.recommended_channel else None
                    ),
                    confidence=best.confidence.value,
                    reasons=(*best.reasons, *notes),
                    policy_version=policy,
                    event=DecisionMakerSelected(
                        opportunity_id=opportunity_id,
                        company_id=company_id,
                        contact_id=best.contact_id,
                        recommended_channel=(
                            best.recommended_channel.value if best.recommended_channel else None
                        ),
                        policy_version=policy,
                    ),
                )
            if best.total_score >= self._thresholds.review_score:
                return DecisionMakerSelectionOutcome(
                    action=DecisionMakerSelectionAction.REVIEW,
                    company_id=company_id,
                    opportunity_id=opportunity_id,
                    ranked_candidates=ranked,
                    confidence=best.confidence.value,
                    reasons=(
                        "best candidate is plausible but below the selection bar — human review",
                        *notes,
                    ),
                    policy_version=policy,
                )
            return DecisionMakerSelectionOutcome(
                action=DecisionMakerSelectionAction.RESEARCH_MORE,
                company_id=company_id,
                opportunity_id=opportunity_id,
                ranked_candidates=ranked,
                confidence=best.confidence.value,
                reasons=(
                    "no candidate fits the logistics-decision-maker profile yet — "
                    "collect better contacts",
                    *notes,
                ),
                policy_version=policy,
            )
