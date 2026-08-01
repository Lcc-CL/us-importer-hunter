"""Persistent prospect orchestration, submission, and resumable execution."""

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.clock import utcnow
from app.domain.contact import RawContactSnapshot
from app.domain.events import CompanyFactsChanged, ContactCandidateDiscovered
from app.domain.exceptions import DuplicateOperation
from app.domain.prospect_batch import (
    PIPELINE_VERSION,
    ProspectBatch,
    ProspectBatchCompany,
    ProspectBatchCompanyStatus,
    ProspectBatchStage,
)
from app.domain.prospect_job import ProspectJob
from app.domain.repositories import ProspectBatchUnitOfWork
from app.domain.research import OutputLanguage, PromotionDecision, ResearchRun
from app.domain.services import SenderProfile
from app.domain.values import QualificationDecision, SourceReference
from app.services.contact_discovery import DiscoverySourceType, department_display_name
from app.services.contact_discovery_runner import ContactDiscoveryRunOutcome
from app.services.email import EmailGenerationError
from app.shared.exceptions import (
    ApplicationConflictError,
    EvidenceReviewIncompleteError,
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
class ProspectBatchSubmission:
    batch: ProspectBatch
    job: ProspectJob
    reused: bool


@dataclass(frozen=True)
class RetryProspectCompanyCommand:
    sender: SenderProfile | None = None


@dataclass(frozen=True)
class ResumeProspectCompanyCommand:
    sender: SenderProfile | None = None


@dataclass(frozen=True)
class EvidenceBlocker:
    claim_position: int
    status: str
    decision: str | None
    kind: str
    detail: str
    evidence_snippet: str
    source_url: str
    fetched_at: datetime
    confidence: float


@dataclass(frozen=True)
class ProspectCompanyBlockers:
    batch_id: UUID
    company_id: UUID
    research_id: UUID
    blocking_claim_count: int
    pending_claim_count: int
    claims: tuple[EvidenceBlocker, ...]


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
ProgressHeartbeat = Callable[[], Awaitable[None]]


class ProspectBatchSubmissionWorkflow:
    """Atomically persist a Batch and one active PostgreSQL execution Job."""

    def __init__(
        self,
        uow_factory: Callable[[], ProspectBatchUnitOfWork],
        *,
        max_attempts: int = 3,
    ) -> None:
        self._uow_factory = uow_factory
        self._max_attempts = max_attempts

    async def submit(
        self,
        discovery_task_id: UUID,
        command: CreateProspectBatchCommand,
        *,
        idempotency_key: str | None,
    ) -> ProspectBatchSubmission:
        selected_ids = _selected_company_ids(command)
        business_key = _business_key(discovery_task_id, selected_ids)
        request_key_hash = _request_key_hash(idempotency_key)
        try:
            async with self._uow_factory() as uow:
                reused = await _find_reused_submission(
                    uow,
                    business_key=business_key,
                    request_key_hash=request_key_hash,
                )
                if reused is not None:
                    return reused
                batch = await _create_new_batch(uow, discovery_task_id, command)
                await uow.flush()
                job = ProspectJob.create(
                    batch_id=batch.id,
                    business_key=business_key,
                    request_key_hash=request_key_hash,
                    sender=command.sender,
                    max_attempts=self._max_attempts,
                )
                await uow.prospect_jobs.add(job)
                await uow.commit()
                return ProspectBatchSubmission(batch=batch, job=job, reused=False)
        except DuplicateOperation:
            async with self._uow_factory() as uow:
                reused = await _find_reused_submission(
                    uow,
                    business_key=business_key,
                    request_key_hash=request_key_hash,
                )
            if reused is None:
                raise
            return reused

    async def retry_company(
        self,
        batch_id: UUID,
        company_id: UUID,
        command: RetryProspectCompanyCommand,
    ) -> ProspectBatchSubmission:
        async with self._uow_factory() as uow:
            batch = await uow.prospect_batches.get_by_id_for_update(batch_id)
            if batch is None:
                raise ResourceNotFoundError(f"prospect batch not found: {batch_id}")
            company = _batch_company(batch, company_id)
            if company.status not in {
                ProspectBatchCompanyStatus.FAILED,
                ProspectBatchCompanyStatus.NEEDS_REVIEW,
            }:
                raise ApplicationConflictError(
                    f"company in {company.status.value} cannot be retried"
                )
            run = (
                await uow.research_runs.get_by_id(company.research_id)
                if company.research_id is not None
                else None
            )
            pending_claim_count = _pending_claim_count(run) if run is not None else 0
            if pending_claim_count:
                raise EvidenceReviewIncompleteError(pending_claim_count=pending_claim_count)
            if company.error_code not in RETRYABLE_ERROR_CODES:
                raise ApplicationConflictError(
                    f"company error {company.error_code or 'unknown'} requires review, not retry"
                )
            batch.replace_company(company.retry())
            batch.queue_for_execution()
            job = _new_execution_job(
                batch,
                sender=command.sender,
                max_attempts=self._max_attempts,
            )
            await uow.prospect_batches.save(batch)
            await uow.prospect_jobs.add(job)
            await uow.commit()
            return ProspectBatchSubmission(batch=batch, job=job, reused=False)

    async def resume_company(
        self,
        batch_id: UUID,
        company_id: UUID,
        command: ResumeProspectCompanyCommand,
    ) -> ProspectBatchSubmission:
        async with self._uow_factory() as uow:
            batch = await uow.prospect_batches.get_by_id_for_update(batch_id)
            if batch is None:
                raise ResourceNotFoundError(f"prospect batch not found: {batch_id}")
            company = _batch_company(batch, company_id)
            if (
                company.status is not ProspectBatchCompanyStatus.NEEDS_REVIEW
                or company.current_stage is not ProspectBatchStage.AWAITING_EVIDENCE_REVIEW
                or company.error_code != "EVIDENCE_REVIEW_REQUIRED"
            ):
                raise ApplicationConflictError(
                    f"company in {company.current_stage.value} cannot be resumed"
                )
            if company.research_id is None:
                raise ApplicationConflictError(
                    "awaiting evidence review company has no saved research run"
                )
            run = await uow.research_runs.get_by_id(company.research_id)
            if run is None:
                raise ResourceNotFoundError(
                    f"research run not found: {company.research_id}"
                )
            pending_claim_count = _pending_claim_count(run)
            if pending_claim_count:
                raise EvidenceReviewIncompleteError(pending_claim_count=pending_claim_count)
            batch.replace_company(company.resume_after_evidence_review())
            batch.queue_for_execution()
            job = _new_execution_job(
                batch,
                sender=command.sender,
                max_attempts=self._max_attempts,
            )
            await uow.prospect_batches.save(batch)
            await uow.prospect_jobs.add(job)
            await uow.commit()
            return ProspectBatchSubmission(batch=batch, job=job, reused=False)


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
        async with self._uow_factory() as uow:
            batch = await _create_new_batch(uow, discovery_task_id, command)
            await uow.commit()

        return await self.execute(batch.id, sender=command.sender)

    async def execute(
        self,
        batch_id: UUID,
        *,
        sender: SenderProfile | None,
        heartbeat: ProgressHeartbeat | None = None,
    ) -> ProspectBatch:
        batch = await self._require_batch(batch_id)
        if not batch.has_active_companies:
            return batch
        await self._start_batch(batch.id)
        for batch_company in batch.companies:
            if batch_company.status in {
                ProspectBatchCompanyStatus.COMPLETED,
                ProspectBatchCompanyStatus.NEEDS_REVIEW,
                ProspectBatchCompanyStatus.FAILED,
            }:
                continue
            await _notify(heartbeat)
            try:
                if batch_company.research_id is None:
                    await self._process_company(
                        batch.id,
                        batch_company.company_id,
                        sender,
                        heartbeat=heartbeat,
                    )
                else:
                    run = await self._get_research(batch_company.research_id)
                    if run is None:
                        raise ResourceNotFoundError(
                            f"research run not found: {batch_company.research_id}"
                        )
                    pending_claim_count = _pending_claim_count(run)
                    if pending_claim_count:
                        await self._await_evidence_review(
                            batch.id,
                            batch_company.company_id,
                            blocking_claim_count=pending_claim_count,
                        )
                    else:
                        await self._process_after_research(
                            batch.id,
                            batch_company.company_id,
                            run,
                            sender,
                            resumed_after_review=batch_company.resume_count > 0,
                            heartbeat=heartbeat,
                        )
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
            await _notify(heartbeat)
        latest = await self._require_batch(batch.id)
        if latest.has_active_companies:
            return latest
        await self._finalize(batch.id)
        return await self._require_batch(batch.id)

    async def retry(
        self,
        batch_id: UUID,
        company_id: UUID,
        command: RetryProspectCompanyCommand,
    ) -> ProspectBatch:
        reuse_research_id: UUID | None = None
        async with self._uow_factory() as uow:
            batch = await uow.prospect_batches.get_by_id_for_update(batch_id)
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
            run = (
                await uow.research_runs.get_by_id(company.research_id)
                if company.research_id is not None
                else None
            )
            pending_claim_count = _pending_claim_count(run) if run is not None else 0
            if pending_claim_count:
                raise EvidenceReviewIncompleteError(
                    pending_claim_count=pending_claim_count
                )
            if company.error_code not in RETRYABLE_ERROR_CODES:
                raise ApplicationConflictError(
                    f"company error {company.error_code or 'unknown'} requires review, not retry"
                )
            if company.error_code not in {
                "WEBSITE_MISSING",
                "WEBSITE_INVALID",
                "RESEARCH_FAILED",
                "RESEARCH_INCOMPLETE",
            }:
                reuse_research_id = company.research_id
            batch.replace_company(company.retry())
            batch.start()
            await uow.prospect_batches.save(batch)
            await uow.commit()

        try:
            if reuse_research_id is None:
                await self._process_company(batch_id, company_id, command.sender)
            else:
                run = await self._get_research(reuse_research_id)
                if run is None:
                    raise ResourceNotFoundError(
                        f"research run not found: {reuse_research_id}"
                    )
                await self._process_after_research(
                    batch_id,
                    company_id,
                    run,
                    command.sender,
                    resumed_after_review=False,
                )
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

    async def resume(
        self,
        batch_id: UUID,
        company_id: UUID,
        command: ResumeProspectCompanyCommand,
    ) -> ProspectBatch:
        async with self._uow_factory() as uow:
            batch = await uow.prospect_batches.get_by_id_for_update(batch_id)
            if batch is None:
                raise ResourceNotFoundError(f"prospect batch not found: {batch_id}")
            try:
                company = batch.company(company_id)
            except Exception as exc:
                raise ResourceNotFoundError(
                    f"company {company_id} is not in prospect batch {batch_id}"
                ) from exc
            if (
                company.status is not ProspectBatchCompanyStatus.NEEDS_REVIEW
                or company.current_stage is not ProspectBatchStage.AWAITING_EVIDENCE_REVIEW
                or company.error_code != "EVIDENCE_REVIEW_REQUIRED"
            ):
                raise ApplicationConflictError(
                    f"company in {company.current_stage.value} cannot be resumed"
                )
            if company.research_id is None:
                raise ApplicationConflictError(
                    "awaiting evidence review company has no saved research run"
                )
            run = await uow.research_runs.get_by_id(company.research_id)
            if run is None:
                raise ResourceNotFoundError(
                    f"research run not found: {company.research_id}"
                )
            pending_claim_count = _pending_claim_count(run)
            if pending_claim_count:
                raise EvidenceReviewIncompleteError(
                    pending_claim_count=pending_claim_count
                )

            batch.replace_company(company.resume_after_evidence_review())
            batch.start()
            await uow.prospect_batches.save(batch)
            await uow.commit()

        try:
            await self._process_after_research(
                batch_id,
                company_id,
                run,
                command.sender,
                resumed_after_review=True,
            )
        except Exception as exc:
            logger.exception("prospect batch resume failed unexpectedly")
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
        self,
        batch_id: UUID,
        company_id: UUID,
        sender: SenderProfile | None,
        *,
        heartbeat: ProgressHeartbeat | None = None,
    ) -> None:
        await self._stage(batch_id, company_id, ProspectBatchStage.VALIDATING)
        await _notify(heartbeat)
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
        await _notify(heartbeat)
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
        await _notify(heartbeat)
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
        pending_claim_count = _pending_claim_count(run)
        if pending_claim_count:
            await self._await_evidence_review(
                batch_id,
                company_id,
                blocking_claim_count=pending_claim_count,
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

        await self._process_after_research(
            batch_id,
            company_id,
            run,
            sender,
            resumed_after_review=False,
            heartbeat=heartbeat,
        )

    async def _process_after_research(
        self,
        batch_id: UUID,
        company_id: UUID,
        run: ResearchRun,
        sender: SenderProfile | None,
        *,
        resumed_after_review: bool,
        heartbeat: ProgressHeartbeat | None = None,
    ) -> None:
        current = await self._require_company(batch_id, company_id)
        opportunity_id = current.opportunity_id
        qualification_decision = current.qualification_decision
        if opportunity_id is None:
            await self._stage(batch_id, company_id, ProspectBatchStage.SCORING)
            await _notify(heartbeat)
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
            qualification_decision = opportunity.qualification_decision
            assert opportunity_id is not None
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
            await _notify(heartbeat)
        assert opportunity_id is not None
        if qualification_decision == QualificationDecision.DISQUALIFIED.value:
            await self._terminal(
                batch_id,
                company_id,
                failed=False,
                code="COMPANY_DISQUALIFIED",
                summary="opportunity scoring marked the company disqualified",
            )
            return
        if qualification_decision != QualificationDecision.QUALIFIED.value:
            await self._terminal(
                batch_id,
                company_id,
                failed=False,
                code=(
                    "INSUFFICIENT_TRUSTED_EVIDENCE"
                    if resumed_after_review
                    else "OPPORTUNITY_NOT_QUALIFIED"
                ),
                summary=(
                    "reviewed evidence is still insufficient for qualified outreach"
                    if resumed_after_review
                    else "opportunity requires more evidence or human review before outreach"
                ),
            )
            return

        current = await self._require_company(batch_id, company_id)
        selected_contact_id = current.selected_contact_id
        if selected_contact_id is None:
            await self._stage(batch_id, company_id, ProspectBatchStage.DISCOVERING_CONTACT)
            await _notify(heartbeat)
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
            await _notify(heartbeat)

        assert selected_contact_id is not None
        current = await self._require_company(batch_id, company_id)
        if current.outreach_id is not None and current.draft_version is not None:
            await self._mutate(batch_id, company_id, lambda _batch, item: item.complete())
            await _notify(heartbeat)
            return
        await self._stage(batch_id, company_id, ProspectBatchStage.GENERATING_DRAFT)
        await _notify(heartbeat)
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
                opportunity_id=opportunity_id,
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
        await _notify(heartbeat)

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

    async def _await_evidence_review(
        self,
        batch_id: UUID,
        company_id: UUID,
        *,
        blocking_claim_count: int,
    ) -> None:
        await self._mutate(
            batch_id,
            company_id,
            lambda _batch, item: item.await_evidence_review(
                blocking_claim_count=blocking_claim_count
            ),
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

    async def _require_company(
        self, batch_id: UUID, company_id: UUID
    ) -> ProspectBatchCompany:
        batch = await self._require_batch(batch_id)
        return batch.company(company_id)


class ProspectBatchQueryWorkflow:
    def __init__(self, uow_factory: Callable[[], ProspectBatchUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def get(self, batch_id: UUID) -> ProspectBatch | None:
        async with self._uow_factory() as uow:
            return await uow.prospect_batches.get_by_id(batch_id)

    async def blockers(
        self, batch_id: UUID, company_id: UUID
    ) -> ProspectCompanyBlockers:
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
            if company.research_id is None:
                raise ResourceNotFoundError(
                    f"company {company_id} has no saved research run"
                )
            run = await uow.research_runs.get_by_id(company.research_id)
        if run is None:
            raise ResourceNotFoundError(
                f"research run not found: {company.research_id}"
            )

        promotions = {item.claim_position: item for item in run.promotions}
        pages = {item.position: item for item in run.pages}
        claims: list[EvidenceBlocker] = []
        for claim in run.claims:
            promotion = promotions.get(claim.position)
            page = pages[claim.source_page_position]
            if promotion is None:
                review_status = "pending"
                decision = None
            elif promotion.decision is PromotionDecision.REJECTED:
                review_status = "rejected"
                decision = promotion.decision.value
            else:
                review_status = "accepted"
                decision = promotion.decision.value
            claims.append(
                EvidenceBlocker(
                    claim_position=claim.position,
                    status=review_status,
                    decision=decision,
                    kind=claim.kind,
                    detail=claim.detail,
                    evidence_snippet=claim.evidence_snippet,
                    source_url=page.final_url,
                    fetched_at=page.fetched_at,
                    confidence=claim.confidence,
                )
            )
        pending_claim_count = sum(item.status == "pending" for item in claims)
        return ProspectCompanyBlockers(
            batch_id=batch.id,
            company_id=company.company_id,
            research_id=run.id,
            blocking_claim_count=company.blocking_claim_count,
            pending_claim_count=pending_claim_count,
            claims=tuple(claims),
        )


def _pending_claim_count(run: ResearchRun) -> int:
    reviewed_positions = {promotion.claim_position for promotion in run.promotions}
    return sum(claim.position not in reviewed_positions for claim in run.claims)


def _selected_company_ids(command: CreateProspectBatchCommand) -> tuple[UUID, ...]:
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
    return unique_ids[: min(command.limit, MAX_BATCH_COMPANIES)]


async def _create_new_batch(
    uow: ProspectBatchUnitOfWork,
    discovery_task_id: UUID,
    command: CreateProspectBatchCommand,
) -> ProspectBatch:
    selected_ids = _selected_company_ids(command)
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
    outside = [company_id for company_id in selected_ids if company_id not in task_companies]
    if outside:
        raise InvalidInputError(
            code="BATCH_COMPANY_OUTSIDE_TASK",
            message=(
                "company_ids must all belong to this discovery task: "
                + ", ".join(str(value) for value in outside)
            ),
        )

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
        requested_count=len(command.company_ids),
        companies=tuple(companies),
    )
    await uow.prospect_batches.add(batch)
    return batch


def _business_key(discovery_task_id: UUID, company_ids: tuple[UUID, ...]) -> str:
    canonical = json.dumps(
        {
            "discovery_task_id": str(discovery_task_id),
            "company_ids": sorted(str(company_id) for company_id in company_ids),
            "pipeline_version": PIPELINE_VERSION,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _request_key_hash(idempotency_key: str | None) -> str | None:
    if idempotency_key is None:
        return None
    normalized = idempotency_key.strip()
    if not normalized:
        raise InvalidInputError(
            code="IDEMPOTENCY_KEY_INVALID",
            message="Idempotency-Key must not be blank",
        )
    if len(normalized) > 200:
        raise InvalidInputError(
            code="IDEMPOTENCY_KEY_INVALID",
            message="Idempotency-Key must be at most 200 characters",
        )
    return hashlib.sha256(normalized.encode()).hexdigest()


async def _find_reused_submission(
    uow: ProspectBatchUnitOfWork,
    *,
    business_key: str,
    request_key_hash: str | None,
) -> ProspectBatchSubmission | None:
    job = (
        await uow.prospect_jobs.find_by_request_key_hash(request_key_hash)
        if request_key_hash is not None
        else None
    )
    if job is not None and job.business_key != business_key:
        raise ApplicationConflictError("Idempotency-Key was already used for another batch")
    if job is None:
        job = await uow.prospect_jobs.find_active_by_business_key(business_key)
    if job is None:
        return None
    batch = await uow.prospect_batches.get_by_id(job.batch_id)
    if batch is None:
        raise ResourceNotFoundError(f"prospect batch not found: {job.batch_id}")
    return ProspectBatchSubmission(batch=batch, job=job, reused=True)


def _new_execution_job(
    batch: ProspectBatch,
    *,
    sender: SenderProfile | None,
    max_attempts: int,
) -> ProspectJob:
    company_ids = tuple(company.company_id for company in batch.companies)
    return ProspectJob.create(
        batch_id=batch.id,
        business_key=_business_key(batch.discovery_task_id, company_ids),
        request_key_hash=None,
        sender=sender,
        max_attempts=max_attempts,
    )


def _batch_company(batch: ProspectBatch, company_id: UUID) -> ProspectBatchCompany:
    try:
        return batch.company(company_id)
    except Exception as exc:
        raise ResourceNotFoundError(
            f"company {company_id} is not in prospect batch {batch.id}"
        ) from exc


async def _notify(heartbeat: ProgressHeartbeat | None) -> None:
    if heartbeat is not None:
        await heartbeat()
