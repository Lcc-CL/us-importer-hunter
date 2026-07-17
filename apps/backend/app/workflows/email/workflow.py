"""Email draft generation workflow: the MVP core chain's last hop.

    (opportunity_id, contact_id, sender profile)
      → Opportunity must be QUALIFIED (latest assessment)
      → Company facts + ACTIVE Contact
      → minimal EmailGenerationContext (+ stable fingerprint)
      → same fingerprint + prompt already drafted? → SKIPPED
      → EmailDraftGenerator (fake in tests; OpenAI in real runs)
      → new EmailDraft version on the Outreach (never overwrites)
      → peek → commit → drain (L9 rule)

Never sends anything — a human reviews every draft (GENERATED status).
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.contact import ContactStatus
from app.domain.events import DomainEvent
from app.domain.exceptions import DuplicateOperation
from app.domain.outreach import Outreach
from app.domain.repositories import UnitOfWork
from app.domain.services import (
    EmailDraftGenerator,
    EmailGenerationContext,
    SenderProfile,
)
from app.domain.values import QualificationDecision
from app.prompts.sales.first_outreach import PROMPT_VERSION


class EmailDraftAction(StrEnum):
    GENERATED = "generated"
    SKIPPED = "skipped"
    REJECTED = "rejected"


@dataclass(frozen=True)
class EmailDraftOutcome:
    action: EmailDraftAction
    opportunity_id: UUID
    outreach_id: UUID | None = None
    draft_version: int | None = None
    subject: str | None = None
    body: str | None = None
    status: str | None = None
    notes: tuple[str, ...] = ()
    emitted_events_count: int = 0


class EmailDraftGenerationWorkflow:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        generator: EmailDraftGenerator,
    ) -> None:
        self._uow_factory = uow_factory
        self._generator = generator

    async def handle(
        self, *, opportunity_id: UUID, contact_id: UUID, sender: SenderProfile
    ) -> EmailDraftOutcome:
        async with self._uow_factory() as uow:
            opportunity = await uow.opportunities.get_by_id(opportunity_id)
            if opportunity is None:
                return self._rejected(opportunity_id, "opportunity not found")
            if not opportunity.history:
                return self._rejected(opportunity_id, "opportunity has no assessment yet")
            latest = opportunity.history[-1]
            if latest.qualification_decision is not QualificationDecision.QUALIFIED:
                decision = (
                    latest.qualification_decision.value
                    if latest.qualification_decision
                    else "unknown"
                )
                return self._rejected(
                    opportunity_id,
                    f"only QUALIFIED opportunities get drafts — this one is {decision}",
                )

            company = await uow.companies.get_by_id(opportunity.company_id)
            if company is None:
                return self._rejected(opportunity_id, "company not found")

            contact = await uow.contacts.get_by_id(contact_id)
            if contact is None:
                return self._rejected(opportunity_id, "contact not found")
            if contact.status is not ContactStatus.ACTIVE:
                return self._rejected(
                    opportunity_id,
                    f"contact is {contact.status.value} — drafts go to ACTIVE contacts only",
                )

            context = EmailGenerationContext(
                company_name=company.name.value,
                website=company.website.value if company.website else None,
                contact_name=contact.name.value,
                contact_title=contact.title.raw if contact.title else None,
                opportunity_score=latest.new_score.value,
                qualification_decision=latest.qualification_decision.value,
                opportunity_reasons=latest.reasons,
                available_evidence=tuple(e.claim for e in latest.evidence),
                sender_name=sender.name,
                sender_company=sender.company,
                sender_value_proposition=sender.value_proposition,
            )
            fingerprint = context.fingerprint()

            outreach = self._pick_outreach(
                await uow.outreaches.list_for_opportunity(opportunity_id), contact_id
            )
            existing_draft = (
                next(
                    (
                        draft
                        for draft in outreach.drafts
                        if draft.context_fingerprint == fingerprint
                        and draft.prompt_version == PROMPT_VERSION
                    ),
                    None,
                )
                if outreach is not None
                else None
            )
            if outreach is not None and existing_draft is not None:
                return EmailDraftOutcome(
                    action=EmailDraftAction.SKIPPED,
                    opportunity_id=opportunity_id,
                    outreach_id=outreach.id,
                    draft_version=existing_draft.version,
                    subject=existing_draft.subject,
                    body=existing_draft.body,
                    status=existing_draft.status.value,
                    notes=("identical context already drafted — review the existing version",),
                )

            email = await self._generator.generate(context)  # crash → rollback, nothing saved

            is_new_outreach = outreach is None
            if outreach is None:
                outreach = Outreach.create(opportunity_id)
                outreach.attach_contact(contact_id)
            try:
                draft = outreach.add_draft(
                    email.subject,
                    email.body,
                    PROMPT_VERSION,
                    provider=self._generator.provider_name,
                    model=self._generator.model_name,
                    context_fingerprint=fingerprint,
                )
            except DuplicateOperation as exc:
                return EmailDraftOutcome(
                    action=EmailDraftAction.SKIPPED,
                    opportunity_id=opportunity_id,
                    outreach_id=outreach.id,
                    notes=(str(exc),),
                )
            if is_new_outreach:
                await uow.outreaches.add(outreach)
            else:
                await uow.outreaches.save(outreach)

            pending = len(outreach.pending_events)
            try:
                await uow.commit()
            except DuplicateOperation:
                return EmailDraftOutcome(
                    action=EmailDraftAction.SKIPPED,
                    opportunity_id=opportunity_id,
                    outreach_id=outreach.id,
                    notes=(
                        "concurrent duplicate draft rejected — review the existing version",
                    ),
                )
            events: tuple[DomainEvent, ...] = outreach.drain_events()
            assert len(events) == pending

            return EmailDraftOutcome(
                action=EmailDraftAction.GENERATED,
                opportunity_id=opportunity_id,
                outreach_id=outreach.id,
                draft_version=draft.version,
                subject=draft.subject,
                body=draft.body,
                status=draft.status.value,
                notes=(f"draft awaits human review ({draft.status.value})",),
                emitted_events_count=len(events),
            )

    @staticmethod
    def _pick_outreach(candidates: list[Outreach], contact_id: UUID) -> Outreach | None:
        for outreach in candidates:
            if outreach.contact_id == contact_id and outreach.status.value not in ("won", "lost"):
                return outreach
        return None

    @staticmethod
    def _rejected(opportunity_id: UUID, note: str) -> EmailDraftOutcome:
        return EmailDraftOutcome(
            action=EmailDraftAction.REJECTED, opportunity_id=opportunity_id, notes=(note,)
        )
