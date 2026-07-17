"""Synchronous MVP prospect facade over the existing application workflows.

Each child workflow owns its transaction. The facade coordinates typed outcomes,
never opens a session, reads ORM rows, scores, ranks contacts, or builds prompts.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.domain.clock import utcnow
from app.domain.contact import RawContactSnapshot
from app.domain.discovery import DiscoveryResult, RawCompanySnapshot, Signal
from app.domain.events import (
    CompanyDiscovered,
    CompanyFactsChanged,
    CompanyIngested,
    ContactCandidateDiscovered,
)
from app.domain.exceptions import DomainError
from app.domain.repositories import UnitOfWork
from app.domain.services import SenderProfile
from app.domain.values import SourceReference
from app.services.email import EmailGenerationError
from app.workflows.company_ingestion import IngestionOutcome, IngestionStatus
from app.workflows.contact_ingestion import ContactIngestionAction, ContactIngestionOutcome
from app.workflows.decision_maker import (
    DecisionMakerSelectionAction,
    DecisionMakerSelectionOutcome,
)
from app.workflows.email import EmailDraftAction, EmailDraftOutcome
from app.workflows.opportunity import OpportunityProcessingAction, OpportunityProcessingOutcome

logger = logging.getLogger(__name__)

MVP_SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
UowFactory = Callable[[], UnitOfWork]


class OverallStatus(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class StageStatus(StrEnum):
    CREATED = "CREATED"
    MERGED = "MERGED"
    QUALIFIED = "QUALIFIED"
    REVIEW = "REVIEW"
    RESEARCH_MORE = "RESEARCH_MORE"
    SELECTED = "SELECTED"
    GENERATED = "GENERATED"
    SKIPPED = "SKIPPED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ProspectSignalInput:
    kind: str
    detail: str


@dataclass(frozen=True)
class ProspectSourceInput:
    source: str
    reference: str
    retrieved_at: datetime | None = None


@dataclass(frozen=True)
class ProspectCompanyInput:
    name: str
    website: str | None
    signals: tuple[ProspectSignalInput, ...] = ()
    sources: tuple[ProspectSourceInput, ...] = ()
    source: str | None = None  # legacy API input; website is its real reference


@dataclass(frozen=True)
class ProspectContactInput:
    name: str
    source: str
    title: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    phone: str | None = None


@dataclass(frozen=True)
class MvpProspectAnalysisCommand:
    request_id: str
    company: ProspectCompanyInput
    sender: SenderProfile
    contact: ProspectContactInput | None = None
    generate_email: bool = True


@dataclass(frozen=True)
class CompanyStageResult:
    action: StageStatus
    name: str
    company_id: UUID | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpportunityStageResult:
    action: StageStatus
    opportunity_id: UUID | None = None
    score: float | None = None
    confidence: float | None = None
    data_completeness: float | None = None
    qualification_decision: str | None = None
    recommended_action: str | None = None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContactStageResult:
    action: StageStatus
    contact_id: UUID | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionMakerStageResult:
    action: StageStatus
    selected_contact_id: UUID | None = None
    recommended_channel: str | None = None
    confidence: float | None = None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class EmailDraftStageResult:
    action: StageStatus
    outreach_id: UUID | None = None
    version: int | None = None
    subject: str | None = None
    body: str | None = None
    status: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class MvpProspectAnalysisOutcome:
    request_id: str
    overall_status: OverallStatus
    company: CompanyStageResult
    opportunity: OpportunityStageResult
    contact: ContactStageResult
    decision_maker: DecisionMakerStageResult
    email_draft: EmailDraftStageResult
    warnings: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utcnow)


class CompanyIngestionPort(Protocol):
    async def handle(self, event: CompanyDiscovered) -> IngestionOutcome: ...


class OpportunityPort(Protocol):
    async def handle(
        self,
        event: CompanyIngested | CompanyFactsChanged,
        *,
        user_id: UUID,
        user_lens_version: str | None = None,
    ) -> OpportunityProcessingOutcome: ...


class ContactIngestionPort(Protocol):
    async def handle(self, event: ContactCandidateDiscovered) -> ContactIngestionOutcome: ...


class DecisionMakerPort(Protocol):
    async def handle(
        self, *, company_id: UUID, opportunity_id: UUID
    ) -> DecisionMakerSelectionOutcome: ...


class EmailDraftPort(Protocol):
    async def handle(
        self, *, opportunity_id: UUID, contact_id: UUID, sender: SenderProfile
    ) -> EmailDraftOutcome: ...


class MvpProspectAnalysisWorkflow:
    """Coordinates the already-tested MVP seams and preserves partial success."""

    def __init__(
        self,
        company_ingestion: CompanyIngestionPort,
        opportunity: OpportunityPort,
        contact_ingestion: ContactIngestionPort,
        decision_maker: DecisionMakerPort,
        email_draft: EmailDraftPort,
        *,
        user_id: UUID = MVP_SYSTEM_USER_ID,
    ) -> None:
        self._company_ingestion = company_ingestion
        self._opportunity = opportunity
        self._contact_ingestion = contact_ingestion
        self._decision_maker = decision_maker
        self._email_draft = email_draft
        self._user_id = user_id

    async def handle(self, command: MvpProspectAnalysisCommand) -> MvpProspectAnalysisOutcome:
        created_at = utcnow()
        skipped_opportunity = OpportunityStageResult(action=StageStatus.SKIPPED)
        skipped_contact = ContactStageResult(action=StageStatus.SKIPPED)
        skipped_decision = DecisionMakerStageResult(action=StageStatus.SKIPPED)
        skipped_email = EmailDraftStageResult(action=StageStatus.SKIPPED)

        company_outcomes: list[IngestionOutcome] = []
        try:
            for source in self._company_sources(command.company, created_at):
                company_event = self._company_event(command, source, created_at)
                company_outcomes.append(await self._company_ingestion.handle(company_event))
        except DomainError as exc:
            if company_outcomes:
                company = self._map_company(
                    self._combine_company_outcomes(company_outcomes), command.company.name
                )
                return self._partial_after_company(
                    command,
                    created_at,
                    company,
                    f"a company source was rejected: {exc}",
                )
            return MvpProspectAnalysisOutcome(
                request_id=command.request_id,
                overall_status=OverallStatus.REJECTED,
                company=CompanyStageResult(
                    action=StageStatus.REJECTED,
                    name=command.company.name,
                    notes=(str(exc),),
                ),
                opportunity=skipped_opportunity,
                contact=skipped_contact,
                decision_maker=skipped_decision,
                email_draft=skipped_email,
                created_at=created_at,
            )
        except Exception:
            logger.exception(
                "MVP company ingestion failed", extra={"request_id": command.request_id}
            )
            if company_outcomes:
                company = self._map_company(
                    self._combine_company_outcomes(company_outcomes), command.company.name
                )
                return self._partial_after_company(
                    command,
                    created_at,
                    company,
                    "company source ingestion failed",
                )
            return MvpProspectAnalysisOutcome(
                request_id=command.request_id,
                overall_status=OverallStatus.FAILED,
                company=CompanyStageResult(
                    action=StageStatus.FAILED,
                    name=command.company.name,
                    notes=("company ingestion failed",),
                ),
                opportunity=skipped_opportunity,
                contact=skipped_contact,
                decision_maker=skipped_decision,
                email_draft=skipped_email,
                warnings=("analysis stopped before persistence completed",),
                created_at=created_at,
            )

        company_outcome = self._combine_company_outcomes(company_outcomes)
        company = self._map_company(company_outcome, command.company.name)
        if company.action is StageStatus.REJECTED or company.company_id is None:
            return MvpProspectAnalysisOutcome(
                request_id=command.request_id,
                overall_status=OverallStatus.REJECTED,
                company=company,
                opportunity=skipped_opportunity,
                contact=skipped_contact,
                decision_maker=skipped_decision,
                email_draft=skipped_email,
                created_at=created_at,
            )
        if any(item.status is IngestionStatus.REJECTED for item in company_outcomes):
            return self._partial_after_company(
                command,
                created_at,
                company,
                "one or more company sources were rejected",
            )

        try:
            if company_outcome.event is None:
                raise RuntimeError("company ingestion returned no continuation event")
            opportunity_outcome = await self._opportunity.handle(
                company_outcome.event, user_id=self._user_id
            )
        except Exception:
            logger.exception(
                "MVP opportunity stage failed", extra={"request_id": command.request_id}
            )
            return self._partial_after_company(
                command, created_at, company, "opportunity analysis failed"
            )

        opportunity = self._map_opportunity(opportunity_outcome)
        if opportunity_outcome.opportunity_id is None:
            return MvpProspectAnalysisOutcome(
                request_id=command.request_id,
                overall_status=OverallStatus.PARTIAL,
                company=company,
                opportunity=opportunity,
                contact=skipped_contact,
                decision_maker=skipped_decision,
                email_draft=skipped_email,
                warnings=("opportunity stage did not produce a persisted opportunity",),
                created_at=created_at,
            )

        if command.contact is None:
            return MvpProspectAnalysisOutcome(
                request_id=command.request_id,
                overall_status=OverallStatus.PARTIAL,
                company=company,
                opportunity=opportunity,
                contact=ContactStageResult(
                    action=StageStatus.RESEARCH_MORE,
                    notes=("no contact was supplied",),
                ),
                decision_maker=DecisionMakerStageResult(
                    action=StageStatus.RESEARCH_MORE,
                    reasons=("a contact is required before decision-maker selection",),
                ),
                email_draft=skipped_email,
                warnings=("analysis saved; contact research is still required",),
                created_at=created_at,
            )

        try:
            contact_outcome = await self._contact_ingestion.handle(
                self._contact_event(command.contact, company.company_id, created_at)
            )
        except DomainError as exc:
            contact = ContactStageResult(action=StageStatus.REJECTED, notes=(str(exc),))
            return self._partial_after_contact(
                command, created_at, company, opportunity, contact, "contact was rejected"
            )
        except Exception:
            logger.exception(
                "MVP contact ingestion failed", extra={"request_id": command.request_id}
            )
            contact = ContactStageResult(
                action=StageStatus.FAILED, notes=("contact ingestion failed",)
            )
            return self._partial_after_contact(
                command, created_at, company, opportunity, contact, "contact ingestion failed"
            )

        contact = self._map_contact(contact_outcome)
        if contact_outcome.contact_id is None or contact.action in (
            StageStatus.REJECTED,
            StageStatus.REVIEW,
        ):
            return self._partial_after_contact(
                command,
                created_at,
                company,
                opportunity,
                contact,
                "decision-maker selection requires a canonical contact",
            )

        try:
            decision_outcome = await self._decision_maker.handle(
                company_id=company.company_id,
                opportunity_id=opportunity_outcome.opportunity_id,
            )
        except Exception:
            logger.exception(
                "MVP decision-maker stage failed", extra={"request_id": command.request_id}
            )
            decision = DecisionMakerStageResult(
                action=StageStatus.FAILED, reasons=("decision-maker selection failed",)
            )
            return self._partial_after_decision(
                command, created_at, company, opportunity, contact, decision
            )

        decision = self._map_decision(decision_outcome)
        if decision_outcome.action is not DecisionMakerSelectionAction.SELECTED:
            return self._partial_after_decision(
                command, created_at, company, opportunity, contact, decision
            )

        if not command.generate_email:
            return MvpProspectAnalysisOutcome(
                request_id=command.request_id,
                overall_status=(
                    OverallStatus.COMPLETED
                    if opportunity.action is StageStatus.QUALIFIED
                    else OverallStatus.PARTIAL
                ),
                company=company,
                opportunity=opportunity,
                contact=contact,
                decision_maker=decision,
                email_draft=EmailDraftStageResult(
                    action=StageStatus.SKIPPED,
                    notes=("email generation disabled by request option",),
                ),
                created_at=created_at,
            )

        if opportunity.action is not StageStatus.QUALIFIED:
            return self._partial_after_decision(
                command,
                created_at,
                company,
                opportunity,
                contact,
                decision,
                warning="email generation requires a qualified opportunity",
            )

        assert decision.selected_contact_id is not None
        try:
            email_outcome = await self._email_draft.handle(
                opportunity_id=opportunity_outcome.opportunity_id,
                contact_id=decision.selected_contact_id,
                sender=command.sender,
            )
        except EmailGenerationError:
            logger.warning(
                "MVP email provider unavailable", extra={"request_id": command.request_id}
            )
            email = EmailDraftStageResult(
                action=StageStatus.FAILED,
                notes=("email provider is unavailable; upstream analysis was saved",),
            )
            return self._finish(command, created_at, company, opportunity, contact, decision, email)
        except Exception:
            logger.exception("MVP email stage failed", extra={"request_id": command.request_id})
            email = EmailDraftStageResult(
                action=StageStatus.FAILED,
                notes=("email generation failed; upstream analysis was saved",),
            )
            return self._finish(command, created_at, company, opportunity, contact, decision, email)

        email = self._map_email(email_outcome)
        return self._finish(command, created_at, company, opportunity, contact, decision, email)

    @staticmethod
    def _company_event(
        command: MvpProspectAnalysisCommand,
        source_input: ProspectSourceInput,
        occurred_at: datetime,
    ) -> CompanyDiscovered:
        company = command.company
        source = SourceReference(
            source=source_input.source,
            reference=source_input.reference,
            retrieved_at=source_input.retrieved_at or occurred_at,
        )
        return CompanyDiscovered(
            run_id=UUID(command.request_id),
            occurred_at=occurred_at,
            result=DiscoveryResult(
                snapshot=RawCompanySnapshot(
                    name_text=company.name,
                    website_text=company.website,
                    source=source,
                ),
                signals=tuple(
                    Signal(kind=item.kind, detail=item.detail) for item in company.signals
                ),
            ),
        )

    @staticmethod
    def _company_sources(
        company: ProspectCompanyInput, occurred_at: datetime
    ) -> tuple[ProspectSourceInput, ...]:
        sources = list(company.sources)
        if company.source is not None:
            if company.website is None:
                raise DomainError(
                    "legacy company.source requires company.website as its real reference; "
                    "use company.sources with an explicit reference"
                )
            sources.append(
                ProspectSourceInput(
                    source=company.source,
                    reference=company.website,
                    retrieved_at=occurred_at,
                )
            )
        if not sources:
            raise DomainError("company requires at least one real source reference")

        unique: dict[tuple[str, str], ProspectSourceInput] = {}
        for source in sources:
            key = (source.source.strip(), source.reference.strip())
            unique.setdefault(key, source)
        return tuple(unique.values())

    @staticmethod
    def _combine_company_outcomes(
        outcomes: list[IngestionOutcome],
    ) -> IngestionOutcome:
        if not outcomes:
            raise RuntimeError("company ingestion produced no outcome")
        successful = [item for item in outcomes if item.company_id is not None]
        if not successful:
            return IngestionOutcome(
                status=IngestionStatus.REJECTED,
                company_id=None,
                notes=tuple(note for item in outcomes for note in item.notes),
                event=None,
            )
        last = successful[-1]
        status = (
            IngestionStatus.CREATED
            if any(item.status is IngestionStatus.CREATED for item in successful)
            else IngestionStatus.MERGED
        )
        return IngestionOutcome(
            status=status,
            company_id=last.company_id,
            notes=tuple(note for item in outcomes for note in item.notes),
            event=last.event,
        )

    @staticmethod
    def _contact_event(
        contact: ProspectContactInput, company_id: UUID, occurred_at: datetime
    ) -> ContactCandidateDiscovered:
        reference = contact.linkedin_url or contact.email or contact.phone
        if reference is None:
            raise DomainError(
                "contact source requires a real LinkedIn URL, email address, or phone reference"
            )
        return ContactCandidateDiscovered(
            occurred_at=occurred_at,
            candidate=RawContactSnapshot(
                company_id=company_id,
                raw_name=contact.name,
                raw_title=contact.title,
                raw_email=contact.email,
                raw_linkedin_url=contact.linkedin_url,
                raw_phone=contact.phone,
                source_reference=SourceReference(
                    source=contact.source,
                    reference=reference,
                    retrieved_at=occurred_at,
                ),
            ),
        )

    @staticmethod
    def _map_company(outcome: IngestionOutcome, name: str) -> CompanyStageResult:
        actions = {
            IngestionStatus.CREATED: StageStatus.CREATED,
            IngestionStatus.MERGED: StageStatus.MERGED,
            IngestionStatus.REJECTED: StageStatus.REJECTED,
        }
        return CompanyStageResult(
            action=actions[outcome.status],
            company_id=outcome.company_id,
            name=name.strip(),
            notes=outcome.notes,
        )

    @staticmethod
    def _map_opportunity(outcome: OpportunityProcessingOutcome) -> OpportunityStageResult:
        decision_actions = {
            "qualified": StageStatus.QUALIFIED,
            "review": StageStatus.REVIEW,
            "research_more": StageStatus.RESEARCH_MORE,
            "disqualified": StageStatus.REJECTED,
        }
        action = decision_actions.get(outcome.qualification_decision or "")
        if action is None:
            action = (
                StageStatus.REJECTED
                if outcome.action is OpportunityProcessingAction.REJECTED
                else StageStatus.SKIPPED
            )
        return OpportunityStageResult(
            action=action,
            opportunity_id=outcome.opportunity_id,
            score=outcome.score,
            confidence=outcome.confidence,
            data_completeness=outcome.data_completeness,
            qualification_decision=outcome.qualification_decision,
            recommended_action=outcome.recommended_action,
            reasons=outcome.reasons or outcome.notes,
        )

    @staticmethod
    def _map_contact(outcome: ContactIngestionOutcome) -> ContactStageResult:
        actions = {
            ContactIngestionAction.CREATED: StageStatus.CREATED,
            ContactIngestionAction.MERGED: StageStatus.MERGED,
            ContactIngestionAction.POSSIBLE_MATCH: StageStatus.REVIEW,
            ContactIngestionAction.REJECTED: StageStatus.REJECTED,
        }
        return ContactStageResult(
            action=actions[outcome.action],
            contact_id=outcome.contact_id,
            notes=outcome.notes,
        )

    @staticmethod
    def _map_decision(outcome: DecisionMakerSelectionOutcome) -> DecisionMakerStageResult:
        actions = {
            DecisionMakerSelectionAction.SELECTED: StageStatus.SELECTED,
            DecisionMakerSelectionAction.REVIEW: StageStatus.REVIEW,
            DecisionMakerSelectionAction.RESEARCH_MORE: StageStatus.RESEARCH_MORE,
            DecisionMakerSelectionAction.REJECTED: StageStatus.REJECTED,
        }
        return DecisionMakerStageResult(
            action=actions[outcome.action],
            selected_contact_id=outcome.selected_contact_id,
            recommended_channel=outcome.recommended_channel,
            confidence=outcome.confidence,
            reasons=outcome.reasons,
        )

    @staticmethod
    def _map_email(outcome: EmailDraftOutcome) -> EmailDraftStageResult:
        actions = {
            EmailDraftAction.GENERATED: StageStatus.GENERATED,
            EmailDraftAction.SKIPPED: StageStatus.SKIPPED,
            EmailDraftAction.REJECTED: StageStatus.REJECTED,
        }
        return EmailDraftStageResult(
            action=actions[outcome.action],
            outreach_id=outcome.outreach_id,
            version=outcome.draft_version,
            subject=outcome.subject,
            body=outcome.body,
            status=outcome.status,
            notes=outcome.notes,
        )

    @staticmethod
    def _partial_after_company(
        command: MvpProspectAnalysisCommand,
        created_at: datetime,
        company: CompanyStageResult,
        warning: str,
    ) -> MvpProspectAnalysisOutcome:
        return MvpProspectAnalysisOutcome(
            request_id=command.request_id,
            overall_status=OverallStatus.PARTIAL,
            company=company,
            opportunity=OpportunityStageResult(action=StageStatus.FAILED),
            contact=ContactStageResult(action=StageStatus.SKIPPED),
            decision_maker=DecisionMakerStageResult(action=StageStatus.SKIPPED),
            email_draft=EmailDraftStageResult(action=StageStatus.SKIPPED),
            warnings=(warning,),
            created_at=created_at,
        )

    @staticmethod
    def _partial_after_contact(
        command: MvpProspectAnalysisCommand,
        created_at: datetime,
        company: CompanyStageResult,
        opportunity: OpportunityStageResult,
        contact: ContactStageResult,
        warning: str,
    ) -> MvpProspectAnalysisOutcome:
        return MvpProspectAnalysisOutcome(
            request_id=command.request_id,
            overall_status=OverallStatus.PARTIAL,
            company=company,
            opportunity=opportunity,
            contact=contact,
            decision_maker=DecisionMakerStageResult(action=StageStatus.SKIPPED),
            email_draft=EmailDraftStageResult(action=StageStatus.SKIPPED),
            warnings=(warning,),
            created_at=created_at,
        )

    @staticmethod
    def _partial_after_decision(
        command: MvpProspectAnalysisCommand,
        created_at: datetime,
        company: CompanyStageResult,
        opportunity: OpportunityStageResult,
        contact: ContactStageResult,
        decision: DecisionMakerStageResult,
        warning: str = "a decision maker was not selected",
    ) -> MvpProspectAnalysisOutcome:
        return MvpProspectAnalysisOutcome(
            request_id=command.request_id,
            overall_status=OverallStatus.PARTIAL,
            company=company,
            opportunity=opportunity,
            contact=contact,
            decision_maker=decision,
            email_draft=EmailDraftStageResult(action=StageStatus.SKIPPED),
            warnings=(warning,),
            created_at=created_at,
        )

    @staticmethod
    def _finish(
        command: MvpProspectAnalysisCommand,
        created_at: datetime,
        company: CompanyStageResult,
        opportunity: OpportunityStageResult,
        contact: ContactStageResult,
        decision: DecisionMakerStageResult,
        email: EmailDraftStageResult,
    ) -> MvpProspectAnalysisOutcome:
        complete = email.action in (StageStatus.GENERATED, StageStatus.SKIPPED)
        return MvpProspectAnalysisOutcome(
            request_id=command.request_id,
            overall_status=OverallStatus.COMPLETED if complete else OverallStatus.PARTIAL,
            company=company,
            opportunity=opportunity,
            contact=contact,
            decision_maker=decision,
            email_draft=email,
            warnings=() if complete else ("email draft was not generated",),
            created_at=created_at,
        )
