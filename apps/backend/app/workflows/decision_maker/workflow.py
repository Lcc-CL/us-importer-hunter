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

from app.domain.contact import (
    ContactStatus,
    DecisionMakerFitAssessment,
    Department,
    SelectionThresholds,
)
from app.domain.events import DecisionMakerSelected
from app.domain.exceptions import DuplicateOperation
from app.domain.repositories import UnitOfWork
from app.domain.services import DecisionMakerSelectionService
from app.services.contact.scorer import DecisionMakerSelectionResult
from app.services.contact.selector import select
from app.services.contact.size_provider import DeterministicSizeProvider


class NoSelectionReason(StrEnum):
    """Why no decision maker was chosen, as a code the UI can localize.

    A code rather than a sentence: the domain layer stays language-neutral,
    and the reviewer still gets an explanation in their own language instead
    of an empty result they have to guess about.
    """

    NO_CONTACTS = "no_contacts"
    #: The best candidate is a pure sales role. Deliberately never auto-chosen:
    #: an account manager does not decide who moves the freight.
    SALES_ROLE_ONLY = "sales_role_only"
    #: Plausible, but under the selection bar — a human decides.
    BELOW_SELECTION_BAR = "below_selection_bar"
    #: Too weak to act on at all.
    INSUFFICIENT_ROLE_FIT = "insufficient_role_fit"


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
    #: Why nothing was selected, as a code the UI localizes. None when selected.
    no_selection_reason: NoSelectionReason | None = None
    policy_version: str = ""
    event: DecisionMakerSelected | None = None
    selection_result: DecisionMakerSelectionResult | None = None


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

            size_provider = DeterministicSizeProvider()
            try:
                company = await uow.companies.get_by_id(company_id)
                if company is not None:
                    size_provider.populate(company_id, company.signals)
            except AttributeError:
                pass  # test UOW without companies repository

            if not contacts:
                return DecisionMakerSelectionOutcome(
                    action=DecisionMakerSelectionAction.RESEARCH_MORE,
                    company_id=company_id,
                    opportunity_id=opportunity_id,
                    reasons=("no eligible contacts at this company — find people first",),
                    no_selection_reason=NoSelectionReason.NO_CONTACTS,
                    policy_version=policy,
                )

            ranked = await self._selection.rank(contacts, size_provider=size_provider)
            candidates = self._selection.score_all(contacts)
            selection_result = select(candidates, thresholds=self._thresholds)

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

            if selection_result.review_required:
                return DecisionMakerSelectionOutcome(
                    action=DecisionMakerSelectionAction.REVIEW,
                    company_id=company_id,
                    opportunity_id=opportunity_id,
                    ranked_candidates=ranked,
                    reasons=(*selection_result.review_reasons, *notes),
                    no_selection_reason=NoSelectionReason.BELOW_SELECTION_BAR,
                    policy_version=policy,
                    selection_result=selection_result,
                )

            if selection_result.primary_contact is not None:
                primary = selection_result.primary_contact
                return DecisionMakerSelectionOutcome(
                    action=DecisionMakerSelectionAction.SELECTED,
                    company_id=company_id,
                    opportunity_id=opportunity_id,
                    selected_contact_id=primary.contact_id,
                    ranked_candidates=ranked,
                    recommended_channel=(
                        primary.recommended_channel.value
                        if primary.recommended_channel else None
                    ),
                    confidence=primary.role_classification_confidence,
                    reasons=(*notes,),
                    policy_version=policy,
                    event=DecisionMakerSelected(
                        opportunity_id=opportunity_id,
                        company_id=company_id,
                        contact_id=primary.contact_id,
                        recommended_channel=(
                            primary.recommended_channel.value
                            if primary.recommended_channel else None
                        ),
                        policy_version=policy,
                    ),
                    selection_result=selection_result,
                )

            best = ranked[0]
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
                    no_selection_reason=_no_selection_reason(best),
                    policy_version=policy,
                    selection_result=selection_result,
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
                no_selection_reason=_no_selection_reason(best),
                policy_version=policy,
                selection_result=selection_result,
            )


def _no_selection_reason(best: DecisionMakerFitAssessment) -> NoSelectionReason:
    """Name the blocker so the UI can explain it rather than showing a blank.

    A sales-only candidate is called out separately because it is not a data
    problem the user can fix by finding a better email — it is the right
    person for a different conversation.
    """
    if best.department is Department.SALES_MARKETING:
        return NoSelectionReason.SALES_ROLE_ONLY
    if best.total_score >= SelectionThresholds().review_score:
        return NoSelectionReason.BELOW_SELECTION_BAR
    return NoSelectionReason.INSUFFICIENT_ROLE_FIT
