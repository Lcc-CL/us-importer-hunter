"""Synchronous, persistent D2a orchestration for at most five companies."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.domain.clock import utcnow
from app.domain.contact import RawContactSnapshot
from app.domain.events import CompanyFactsChanged, ContactCandidateDiscovered
from app.domain.prospect_batch import (
    PIPELINE_VERSION,
    ProspectBatch,
    ProspectBatchCompany,
    ProspectBatchCompanyStatus,
    ProspectBatchStage,
)
from app.domain.repositories import ProspectBatchUnitOfWork
from app.domain.research import OutputLanguage, ResearchRun
from app.domain.services import SenderProfile
from app.domain.values import QualificationDecision, SourceReference
from app.services.contact_discovery import DiscoverySourceType, department_display_name
from app.services.contact_discovery_runner import ContactDiscoveryRunOutcome
from app.services.email import EmailGenerationError
from app.shared.exceptions import (
    ApplicationConflictError,
    InvalidInputError,
    ResourceNotFoundError,
)
from app.workflows.contact_ingestion import ContactIngestionAction, ContactIngestionOutcome
from app.workflows.decision_maker import (
    DecisionMakerSelectionAction,
    DecisionMakerSelectionOutcome,
)
from app.workflows.email import EmailDraftAction, EmailDraftOutcome
from app.workflows.mvp_prospect_analysis import MVP_SYSTEM_USER_ID
from app.workflows.opportunity import OpportunityProcessingOutcome
from app.workflows.research import ResearchAction, ResearchOutcome, ResearchRequest

logger = logging.getLogger(__name__)

MAX_BATCH_COMPANIES = 5
RETRYABLE_ERROR_CODES = frozenset(
    {
        "WEBSITE_MISSING",
        "WEBSITE_INVALID",
        "RESEARCH_FAILED",
        "RESEARCH_INCOMPLETE",
        "SCORING_FAILED",
        "SCORING_UNAVAILABLE",
        "CONTACT_DISCOVERY_FAILED",
        "CONTACT_NOT_FOUND",
        "CONTACT_UNUSABLE",
        "DECISION_MAKER_NOT_SELECTED",
        "SENDER_PROFILE_MISSING",
        "DRAFT_GENERATION_FAILED",
        "DRAFT_NOT_GENERATED",
        "PIPELINE_UNEXPECTED_ERROR",
    }
)


@dataclass(frozen=True)
class CreateProspectBatchCommand:
    company_ids: tuple[UUID, ...]
    limit: int = MAX_BATCH_COMPANIES
    sender: SenderProfile | None = None


@dataclass(frozen=True)
class RetryProspectCompanyCommand:
    sender: SenderProfile | None = None


class ResearchPort(Protocol):
    async def handle(self, request: ResearchRequest) -> ResearchOutcome: ...


class OpportunityPort(Protocol):
    async def handle(
        self,
        event: CompanyFactsChanged,
        *,
        user_id: UUID,
        user_lens_version: str | None = None,
    ) -> OpportunityProcessingOutcome: ...


class ContactDiscoveryPort(Protocol):
    async def discover(self, run: ResearchRun) -> ContactDiscoveryRunOutcome: ...


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


BatchMutator = Callable[[ProspectBatch, ProspectBatchCompany], ProspectBatchCompany]


class ProspectBatchWorkflow:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], ProspectBatchUnitOfWork],
        research: ResearchPort,
        opportunity: OpportunityPort,
        contact_discovery: ContactDiscoveryPort,
        contact_ingestion: ContactIngestionPort,
        decision_maker: DecisionMakerPort,
        email_draft: EmailDraftPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._research = research
        self._opportunity = opportunity
        self._contact_discovery = contact_discovery
        self._contact_ingestion = contact_ingestion
        self._decision_maker = decision_maker
        self._email_draft = email_draft

    async def create(
        self, discovery_task_id: UUID, command: CreateProspectBatchCommand
    ) -> ProspectBatch:
        requested_count = len(command.company_ids)
        if requested_count == 0:
            raise InvalidInputError(
                code="BATCH_COMPANIES_REQUIRED",
                message="at least one company_id is required",
            )
        if command.limit < 1:
            raise InvalidInputError(
                code="BATCH_LIMIT_INVALID",
                message="batch limit must be positive",
            )

        unique_ids = tuple(dict.fromkeys(command.company_ids))
        async with self._uow_factory() as uow:
            task = await uow.discovery_tasks.get_by_id(discovery_task_id)
            if task is None:
                raise ResourceNotFoundError(f"discovery task not found: {discovery_task_id}")
            if task.provider != "manual_csv" or task.status.value not in {
                "completed",
                "partial_failed",
            }:
                raise ApplicationConflictError(
                    "batch processing requires a completed or partial_failed manual_csv task"
                )

            task_companies = {
                candidate.company_id: candidate
                for candidate in task.candidates
                if candidate.company_id is not None
            }
            outside = [company_id for company_id in unique_ids if company_id not in task_companies]
            if outside:
                raise InvalidInputError(
                    code="BATCH_COMPANY_OUTSIDE_TASK",
                    message=(
                        "company_ids must all belong to this discovery task: "
                        + ", ".join(str(value) for value in outside)
                    ),
                )

            selected_ids = unique_ids[: min(command.limit, MAX_BATCH_COMPANIES)]
            companies: list[tuple[UUID, str]] = []
            for company_id in selected_ids:
                loaded_company = await uow.companies.get_by_id(company_id)
                if loaded_company is None:
                    raise InvalidInputError(
                        code="BATCH_COMPANY_NOT_FOUND",
                        message=f"company record not found: {company_id}",
                    )
                companies.append((loaded_company.id, loaded_company.name.value))

            batch = ProspectBatch.create(
                discovery_task_id=discovery_task_id,
                requested_count=requested_count,
                companies=tuple(companies),
            )
            await uow.prospect_batches.add(batch)
            await uow.commit()

        await self._start_batch(batch.id)
        for batch_company in batch.companies:
            try:
                await self._process_company(batch.id, batch_company.company_id, command.sender)
            except Exception as exc:  # one company never aborts the remaining batch
                logger.exception(
                    "prospect batch company failed unexpectedly",
                    extra={
                        "batch_id": str(batch.id),
                        "company_id": str(batch_company.company_id),
                    },
                )
                await self._terminal(
                    batch.id,
                    batch_company.company_id,
                    failed=True,
                    code="PIPELINE_UNEXPECTED_ERROR",
                    summary=str(exc) or type(exc).__name__,
                )
        await self._finalize(batch.id)
        return await self._require_batch(batch.id)

    async def retry(
        self,
        batch_id: UUID,
        company_id: UUID,
        command: RetryProspectCompanyCommand,
    ) -> ProspectBatch:
        async with self._uow_factory() as uow:
            batch = await uow.prospect_batches.get_by_id(batch_id)
            if batch is None:
                raise ResourceNotFoundError(f"prospect batch not found: {batch_id}")
            try:
                company = batch.company(company_id)
            except Exception as exc:
                raise ResourceNotFoundError(
                    f"company {company_id} is not in prospect batch {batch_id}"
                ) from exc
            if company.status not in {
                ProspectBatchCompanyStatus.FAILED,
                ProspectBatchCompanyStatus.NEEDS_REVIEW,
            }:
                raise ApplicationConflictError(
                    f"company in {company.status.value} cannot be retried"
                )
            if company.error_code not in RETRYABLE_ERROR_CODES:
                raise ApplicationConflictError(
                    f"company error {company.error_code or 'unknown'} requires review, not retry"
                )
            batch.replace_company(company.retry())
            batch.start()
            await uow.prospect_batches.save(batch)
            await uow.commit()

        try:
            await self._process_company(batch_id, company_id, command.sender)
        except Exception as exc:
            logger.exception("prospect batch retry failed unexpectedly")
            await self._terminal(
                batch_id,
                company_id,
                failed=True,
                code="PIPELINE_UNEXPECTED_ERROR",
                summary=str(exc) or type(exc).__name__,
            )
        await self._finalize(batch_id)
        return await self._require_batch(batch_id)

    async def _process_company(
        self, batch_id: UUID, company_id: UUID, sender: SenderProfile | None
    ) -> None:
        await self._stage(batch_id, company_id, ProspectBatchStage.VALIDATING)
        preflight = await self._preflight(batch_id, company_id)
        if preflight is not None:
            await self._terminal(
                batch_id,
                company_id,
                failed=False,
                code=preflight[0],
                summary=preflight[1],
            )
            return

        await self._stage(batch_id, company_id, ProspectBatchStage.RESEARCHING)
        try:
            research = await self._research.handle(
                ResearchRequest(company_id=company_id, output_language=OutputLanguage.ZH_CN)
            )
        except Exception as exc:
            await self._terminal(
                batch_id,
                company_id,
                failed=True,
                code="RESEARCH_FAILED",
                summary=str(exc) or type(exc).__name__,
            )
            return
        if research.research_id is None:
            await self._terminal(
                batch_id,
                company_id,
                failed=True,
                code="RESEARCH_FAILED",
                summary="research did not persist a run",
            )
            return
        research_id = research.research_id
        await self._mutate(
            batch_id,
            company_id,
            lambda _batch, item: item.with_research(research_id),
        )
        run = await self._get_research(research_id)
        if research.action is ResearchAction.FAILED or run is None:
            await self._terminal(
                batch_id,
                company_id,
                failed=True,
                code="RESEARCH_FAILED",
                summary=(
                    research.failure_code.value if research.failure_code else "research failed"
                ),
            )
            return
        if run.claims_validated > 0 and not run.promotions:
            await self._terminal(
                batch_id,
                company_id,
                failed=False,
                code="EVIDENCE_REVIEW_REQUIRED",
                summary="research claims were saved and require human confirmation",
                stage=ProspectBatchStage.AWAITING_EVIDENCE_REVIEW,
            )
            return
        if research.action is ResearchAction.PARTIAL and run.claims_validated == 0:
            await self._terminal(
                batch_id,
                company_id,
                failed=False,
                code="RESEARCH_INCOMPLETE",
                summary=(
                    research.failure_code.value if research.failure_code else "research incomplete"
                ),
            )
            return

        await self._stage(batch_id, company_id, ProspectBatchStage.SCORING)
        try:
            opportunity = await self._opportunity.handle(
                CompanyFactsChanged(
                    company_id=company_id,
                    changed_fields=("batch_pipeline",),
                    reason=PIPELINE_VERSION,
                ),
                user_id=MVP_SYSTEM_USER_ID,
            )
        except Exception as exc:
            await self._terminal(
                batch_id,
                company_id,
                failed=True,
                code="SCORING_FAILED",
                summary=str(exc) or type(exc).__name__,
            )
            return
        if opportunity.opportunity_id is None:
            await self._terminal(
                batch_id,
                company_id,
                failed=False,
                code="SCORING_UNAVAILABLE",
                summary="scoring did not produce a persisted opportunity",
            )
            return
        opportunity_id = opportunity.opportunity_id
        await self._mutate(
            batch_id,
            company_id,
            lambda _batch, item: item.with_opportunity(
                opportunity_id=opportunity_id,
                score=opportunity.score,
                qualification_decision=opportunity.qualification_decision,
                reasons=opportunity.reasons,
            ),
        )
        if opportunity.qualification_decision == QualificationDecision.DISQUALIFIED.value:
            await self._terminal(
                batch_id,
                company_id,
                failed=False,
                code="COMPANY_DISQUALIFIED",
                summary="opportunity scoring marked the company disqualified",
            )
            return
        if opportunity.qualification_decision != QualificationDecision.QUALIFIED.value:
            await self._terminal(
                batch_id,
                company_id,
                failed=False,
                code="OPPORTUNITY_NOT_QUALIFIED",
                summary="opportunity requires more evidence or human review before outreach",
            )
            return

        await self._stage(batch_id, company_id, ProspectBatchStage.DISCOVERING_CONTACT)
        try:
            discovered = await self._contact_discovery.discover(run)
        except Exception as exc:
            await self._terminal(
                batch_id,
                company_id,
                failed=True,
                code="CONTACT_DISCOVERY_FAILED",
                summary=str(exc) or type(exc).__name__,
            )
            return
        primary = discovered.selection.primary
        if primary is None:
            await self._terminal(
                batch_id,
                company_id,
                failed=False,
                code="CONTACT_NOT_FOUND",
                summary="no usable public contact was found on researched pages",
            )
            return
        contact = primary.contact
        name = contact.name or department_display_name(contact.email)
        try:
            ingested = await self._contact_ingestion.handle(
                ContactCandidateDiscovered(
                    candidate=RawContactSnapshot(
                        company_id=company_id,
                        raw_name=name,
                        raw_title=contact.title or None,
                        raw_email=contact.email or None,
                        raw_phone=contact.phone or None,
                        source_reference=SourceReference(
                            source="company_website",
                            reference=contact.source_url,
                            retrieved_at=utcnow(),
                        ),
                    )
                )
            )
        except Exception as exc:
            await self._terminal(
                batch_id,
                company_id,
                failed=True,
                code="CONTACT_UNUSABLE",
                summary=str(exc) or type(exc).__name__,
            )
            return
        if ingested.contact_id is None or ingested.action in {
            ContactIngestionAction.POSSIBLE_MATCH,
            ContactIngestionAction.REJECTED,
        }:
            await self._terminal(
                batch_id,
                company_id,
                failed=False,
                code="CONTACT_UNUSABLE",
                summary="public contact could not be selected without human review",
            )
            return

        selected_contact_id = ingested.contact_id
        if contact.source_type is not DiscoverySourceType.DEPARTMENT:
            decision = await self._select_decision_maker(
                batch_id,
                company_id,
                opportunity_id,
            )
            if decision is None:
                return
            selected_contact_id = decision
        await self._mutate(
            batch_id,
            company_id,
            lambda _batch, item: item.with_contact(
                contact_id=selected_contact_id,
                name=name,
                email=contact.email or None,
                source_url=contact.source_url,
            ),
        )

        await self._stage(batch_id, company_id, ProspectBatchStage.GENERATING_DRAFT)
        if sender is None:
            await self._terminal(
                batch_id,
                company_id,
                failed=False,
                code="SENDER_PROFILE_MISSING",
                summary="a sender profile is required before draft generation",
            )
            return
        try:
            draft = await self._email_draft.handle(
                opportunity_id=opportunity.opportunity_id,
                contact_id=selected_contact_id,
                sender=sender,
            )
        except EmailGenerationError as exc:
            await self._terminal(
                batch_id,
                company_id,
                failed=True,
                code="DRAFT_GENERATION_FAILED",
                summary=str(exc) or type(exc).__name__,
            )
            return
        except Exception as exc:
            await self._terminal(
                batch_id,
                company_id,
                failed=True,
                code="DRAFT_GENERATION_FAILED",
                summary=str(exc) or type(exc).__name__,
            )
            return
        if (
            draft.action not in {EmailDraftAction.GENERATED, EmailDraftAction.SKIPPED}
            or draft.outreach_id is None
            or draft.draft_version is None
        ):
            await self._terminal(
                batch_id,
                company_id,
                failed=False,
                code="DRAFT_NOT_GENERATED",
                summary="draft prerequisites were not satisfied",
            )
            return
        outreach_id = draft.outreach_id
        draft_version = draft.draft_version
        await self._mutate(
            batch_id,
            company_id,
            lambda _batch, item: item.with_draft(
                outreach_id=outreach_id,
                version=draft_version,
                subject=draft.subject,
                status=draft.status,
            ).complete(),
        )

    async def _select_decision_maker(
        self, batch_id: UUID, company_id: UUID, opportunity_id: UUID
    ) -> UUID | None:
        try:
            decision = await self._decision_maker.handle(
                company_id=company_id,
                opportunity_id=opportunity_id,
            )
        except Exception as exc:
            await self._terminal(
                batch_id,
                company_id,
                failed=True,
                code="DECISION_MAKER_NOT_SELECTED",
                summary=str(exc) or type(exc).__name__,
            )
            return None
        if (
            decision.action is not DecisionMakerSelectionAction.SELECTED
            or decision.selected_contact_id is None
        ):
            await self._terminal(
                batch_id,
                company_id,
                failed=False,
                code="DECISION_MAKER_NOT_SELECTED",
                summary="contact requires human decision-maker review",
            )
            return None
        return decision.selected_contact_id

    async def _preflight(self, batch_id: UUID, company_id: UUID) -> tuple[str, str] | None:
        async with self._uow_factory() as uow:
            batch = await uow.prospect_batches.get_by_id(batch_id)
            assert batch is not None
            task = await uow.discovery_tasks.get_by_id(batch.discovery_task_id)
            company = await uow.companies.get_by_id(company_id)
            if task is None or company is None:
                return "COMPANY_NOT_FOUND", "company or discovery task no longer exists"
            candidate = next(
                (item for item in task.candidates if item.company_id == company_id),
                None,
            )
            if candidate is None:
                return "SOURCE_EVIDENCE_MISSING", "company is not linked to this discovery task"
            if company.website is None:
                if (candidate.website or "").strip():
                    return "WEBSITE_INVALID", "the saved candidate website is not valid HTTP/HTTPS"
                return "WEBSITE_MISSING", "the company has no website or domain"
            source_reference = candidate.source_url or candidate.external_id
            if source_reference is None or not any(
                source.source == candidate.source and source.reference == source_reference
                for source in company.sources
            ):
                return (
                    "SOURCE_EVIDENCE_MISSING",
                    "the discovery task source evidence is not present on the company",
                )
            if await uow.prospect_batches.has_completed_pipeline(
                discovery_task_id=batch.discovery_task_id,
                company_id=company_id,
                pipeline_version=PIPELINE_VERSION,
                exclude_batch_id=batch_id,
            ):
                return "PIPELINE_ALREADY_COMPLETED", "this pipeline version already completed"
        return None

    async def _start_batch(self, batch_id: UUID) -> None:
        async with self._uow_factory() as uow:
            batch = await uow.prospect_batches.get_by_id(batch_id)
            assert batch is not None
            batch.start()
            await uow.prospect_batches.save(batch)
            await uow.commit()

    async def _stage(self, batch_id: UUID, company_id: UUID, stage: ProspectBatchStage) -> None:
        await self._mutate(
            batch_id,
            company_id,
            lambda _batch, item: item.move_to(stage),
        )

    async def _terminal(
        self,
        batch_id: UUID,
        company_id: UUID,
        *,
        failed: bool,
        code: str,
        summary: str,
        stage: ProspectBatchStage = ProspectBatchStage.NEEDS_REVIEW,
    ) -> None:
        await self._mutate(
            batch_id,
            company_id,
            lambda _batch, item: (
                item.fail(error_code=code, error_summary=summary)
                if failed
                else item.needs_review(
                    error_code=code,
                    error_summary=summary,
                    stage=stage,
                )
            ),
        )

    async def _mutate(self, batch_id: UUID, company_id: UUID, mutator: BatchMutator) -> None:
        async with self._uow_factory() as uow:
            batch = await uow.prospect_batches.get_by_id(batch_id)
            assert batch is not None
            item = batch.company(company_id)
            batch.replace_company(mutator(batch, item))
            await uow.prospect_batches.save(batch)
            await uow.commit()

    async def _get_research(self, research_id: UUID) -> ResearchRun | None:
        async with self._uow_factory() as uow:
            return await uow.research_runs.get_by_id(research_id)

    async def _finalize(self, batch_id: UUID) -> None:
        async with self._uow_factory() as uow:
            batch = await uow.prospect_batches.get_by_id(batch_id)
            assert batch is not None
            batch.finalize()
            await uow.prospect_batches.save(batch)
            await uow.commit()

    async def _require_batch(self, batch_id: UUID) -> ProspectBatch:
        async with self._uow_factory() as uow:
            batch = await uow.prospect_batches.get_by_id(batch_id)
        assert batch is not None
        return batch


class ProspectBatchQueryWorkflow:
    def __init__(self, uow_factory: Callable[[], ProspectBatchUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def get(self, batch_id: UUID) -> ProspectBatch | None:
        async with self._uow_factory() as uow:
            return await uow.prospect_batches.get_by_id(batch_id)
