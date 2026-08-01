"""Select, measure and evaluate an existing prospect batch.

No research, scoring, contact discovery or drafting logic lives here. Creation
delegates to the existing D3 submission workflow; reporting reads the persisted
aggregates produced by that workflow and derives a small auditable read model.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.calibration import (
    CalibrationEvaluation,
    CalibrationRun,
    DraftProviderMode,
    ResearchProviderMode,
    WebsiteFetchMode,
)
from app.domain.clock import utcnow
from app.domain.contact import ContactChannelType, ContactVerificationStatus
from app.domain.exceptions import DomainError, DuplicateOperation
from app.domain.outreach import EmailDraftStatus, OutreachStatus
from app.domain.prospect_batch import ProspectBatchCompany, ProspectContactType
from app.domain.prospect_job import ProspectJob
from app.domain.repositories import CalibrationUnitOfWork
from app.domain.research import PromotionDecision, ResearchRun, ResearchRunStatus
from app.domain.services import SenderProfile
from app.domain.values import DimensionStatus, EmailAddress
from app.shared.exceptions import InvalidInputError, ResourceNotFoundError
from app.workflows.prospect_batch import (
    CreateProspectBatchCommand,
    ProspectBatchSubmission,
    ProspectBatchSubmissionWorkflow,
)


@dataclass(frozen=True)
class CalibrationCreateCommand:
    company_ids: tuple[UUID, ...]
    sender: SenderProfile | None = None


@dataclass(frozen=True)
class CalibrationSubmission:
    run: CalibrationRun
    batch_submission: ProspectBatchSubmission
    reused: bool


@dataclass(frozen=True)
class CalibrationEvaluationCommand:
    research_accuracy: int
    opportunity_reasonableness: int
    contact_usability: int
    draft_personalization: int
    draft_professionalism: int
    ready_for_real_outreach: bool
    reviewer_name: str
    notes: str | None = None


@dataclass(frozen=True)
class CalibrationEvaluationView:
    research_accuracy: int
    opportunity_reasonableness: int
    contact_usability: int
    draft_personalization: int
    draft_professionalism: int
    ready_for_real_outreach: bool
    reviewer_name: str
    notes: str | None
    reviewed_at: datetime


@dataclass(frozen=True)
class ResearchMetrics:
    request_succeeded: bool
    pages_fetched: int
    duration_ms: int | None
    new_claim_count: int
    accepted_count: int
    edited_count: int
    rejected_count: int
    pending_count: int
    claims_without_source_count: int
    failure_reason: str | None


@dataclass(frozen=True)
class OpportunityMetrics:
    generated: bool
    score: float | None
    qualification_decision: str | None
    major_positive_reasons: tuple[str, ...]
    major_deduction_reasons: tuple[str, ...]
    limiting_reasons: tuple[str, ...]
    trusted_evidence_count: int
    stopped_for_insufficient_evidence: bool


@dataclass(frozen=True)
class ContactMetrics:
    personal_contact_found: bool
    department_contact_found: bool
    contact_type: str | None
    name: str | None
    title_or_department: str | None
    email: str | None
    phone: str | None
    source_url: str | None
    manually_confirmed: bool
    contact_not_found_reason: str | None


@dataclass(frozen=True)
class DraftFactReport:
    claim: str
    source_urls: tuple[str, ...]
    traceable_to_company_evidence: bool


@dataclass(frozen=True)
class DraftMetrics:
    generated: bool
    not_generated_reason: str | None
    contact_type: str | None
    fact_count: int
    facts: tuple[DraftFactReport, ...]
    all_facts_traceable: bool
    contains_unreviewed_claim: bool
    contains_rejected_claim: bool
    awaiting_human_review: bool
    explicitly_not_sent: bool


@dataclass(frozen=True)
class WorkerMetrics:
    queue_wait_ms: int | None
    total_duration_ms: int | None
    stage_durations_ms: dict[str, int]
    attempt_count: int
    recovery_count: int
    lease_expired: bool
    duplicate_entity_count: int


@dataclass(frozen=True)
class CalibrationCompanyReport:
    company_id: UUID
    company_name: str
    final_status: str
    error_code: str | None
    error_summary: str | None
    research: ResearchMetrics
    opportunity: OpportunityMetrics
    contact: ContactMetrics
    draft: DraftMetrics
    worker: WorkerMetrics
    evaluation: CalibrationEvaluationView | None


@dataclass(frozen=True)
class CalibrationProviderMetrics:
    website_fetch_mode: str
    research_provider_mode: str
    draft_provider_mode: str
    contact_source_mode: str
    paid_request_count: int
    research_provider_call_count: int
    draft_provider_call_count: int
    provider_duration_ms: int
    token_usage_total: int | None


@dataclass(frozen=True)
class CalibrationSummary:
    sample_count: int
    website_research_success_count: int
    website_research_success_rate: float
    evidence_review_company_count: int
    evidence_accepted_count: int
    evidence_rejected_count: int
    opportunity_generated_count: int
    opportunity_generation_rate: float
    qualified_count: int
    personal_contact_count: int
    personal_contact_coverage_rate: float
    department_contact_count: int
    department_contact_coverage_rate: float
    draft_generated_count: int
    draft_generation_rate: float
    ready_for_real_outreach_count: int
    evaluated_company_count: int
    worker_recovery_count: int
    average_processing_duration_ms: int | None
    average_research_accuracy: float | None
    average_opportunity_reasonableness: float | None
    average_contact_usability: float | None
    average_draft_personalization: float | None
    average_draft_professionalism: float | None


@dataclass(frozen=True)
class CalibrationTruthChecks:
    fabricated_contact_count: int
    unreviewed_fact_in_draft_count: int
    rejected_claim_in_score_or_draft_count: int
    pending_claim_bypassed_count: int
    draft_marked_sent_count: int
    duplicate_entity_count: int
    invalid_email_contact_count: int
    website_failure_mislabeled_company_missing_count: int
    opportunity_score_is_probability: bool = False


@dataclass(frozen=True)
class CalibrationReport:
    calibration_id: UUID
    discovery_task_id: UUID
    prospect_batch_id: UUID
    status: str
    sample_source: str
    sample_reality_status: str
    created_at: datetime
    updated_at: datetime
    generated_at: datetime
    providers: CalibrationProviderMetrics
    summary: CalibrationSummary
    truth_checks: CalibrationTruthChecks
    companies: tuple[CalibrationCompanyReport, ...]


class CreateCalibrationRunWorkflow:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], CalibrationUnitOfWork],
        batch_submission: ProspectBatchSubmissionWorkflow,
        website_fetch_mode: WebsiteFetchMode,
        research_provider_mode: ResearchProviderMode,
        draft_provider_mode: DraftProviderMode,
    ) -> None:
        self._uow_factory = uow_factory
        self._batch_submission = batch_submission
        self._website_fetch_mode = website_fetch_mode
        self._research_provider_mode = research_provider_mode
        self._draft_provider_mode = draft_provider_mode

    async def handle(
        self,
        discovery_task_id: UUID,
        command: CalibrationCreateCommand,
        *,
        idempotency_key: str | None,
    ) -> CalibrationSubmission:
        unique_company_ids = tuple(dict.fromkeys(command.company_ids))
        if not 3 <= len(unique_company_ids) <= 5:
            raise InvalidInputError(
                code="CALIBRATION_SAMPLE_SIZE_INVALID",
                message="calibration requires between 3 and 5 unique companies",
            )
        if (
            self._research_provider_mode is ResearchProviderMode.REAL
            or self._draft_provider_mode is DraftProviderMode.REAL
        ):
            raise InvalidInputError(
                code="CALIBRATION_REAL_PROVIDER_REQUIRES_CONTROLLED_RUN",
                message=(
                    "real-provider calibration is disabled until a controlled "
                    "two-company execution path is explicitly enabled"
                ),
            )
        submission = await self._batch_submission.submit(
            discovery_task_id,
            CreateProspectBatchCommand(
                company_ids=unique_company_ids,
                limit=5,
                sender=command.sender,
            ),
            idempotency_key=idempotency_key,
        )
        async with self._uow_factory() as uow:
            existing = await uow.calibrations.get_by_batch_id(submission.batch.id)
            if existing is not None:
                return CalibrationSubmission(
                    run=existing,
                    batch_submission=submission,
                    reused=True,
                )
            run = CalibrationRun.create(
                discovery_task_id=discovery_task_id,
                prospect_batch_id=submission.batch.id,
                sample_count=len(unique_company_ids),
                website_fetch_mode=self._website_fetch_mode,
                research_provider_mode=self._research_provider_mode,
                draft_provider_mode=self._draft_provider_mode,
            )
            await uow.calibrations.add(run)
            try:
                await uow.commit()
            except DuplicateOperation:
                existing = await uow.calibrations.get_by_batch_id(submission.batch.id)
                if existing is None:
                    raise
                return CalibrationSubmission(
                    run=existing,
                    batch_submission=submission,
                    reused=True,
                )
        return CalibrationSubmission(
            run=run,
            batch_submission=submission,
            reused=submission.reused,
        )


class HumanEvaluationWorkflow:
    def __init__(self, uow_factory: Callable[[], CalibrationUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def handle(
        self,
        calibration_id: UUID,
        company_id: UUID,
        command: CalibrationEvaluationCommand,
    ) -> CalibrationEvaluation:
        evaluation = CalibrationEvaluation(
            company_id=company_id,
            research_accuracy=command.research_accuracy,
            opportunity_reasonableness=command.opportunity_reasonableness,
            contact_usability=command.contact_usability,
            draft_personalization=command.draft_personalization,
            draft_professionalism=command.draft_professionalism,
            ready_for_real_outreach=command.ready_for_real_outreach,
            reviewer_name=command.reviewer_name,
            notes=command.notes,
            reviewed_at=utcnow(),
        )
        async with self._uow_factory() as uow:
            run = await uow.calibrations.get_by_id(calibration_id)
            if run is None:
                raise ResourceNotFoundError(f"calibration run not found: {calibration_id}")
            batch = await uow.prospect_batches.get_by_id(run.prospect_batch_id)
            if batch is None:
                raise ResourceNotFoundError(
                    f"prospect batch not found: {run.prospect_batch_id}"
                )
            try:
                batch.company(company_id)
            except DomainError as exc:
                raise ResourceNotFoundError(
                    f"company {company_id} is not in calibration {calibration_id}"
                ) from exc
            run.record_evaluation(evaluation)
            await uow.calibrations.save(run)
            await uow.commit()
        return evaluation


class CalibrationReportWorkflow:
    def __init__(self, uow_factory: Callable[[], CalibrationUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def get(self, calibration_id: UUID) -> CalibrationReport:
        generated_at = utcnow()
        async with self._uow_factory() as uow:
            run = await uow.calibrations.get_by_id(calibration_id)
            if run is None:
                raise ResourceNotFoundError(f"calibration run not found: {calibration_id}")
            batch = await uow.prospect_batches.get_by_id(run.prospect_batch_id)
            if batch is None:
                raise ResourceNotFoundError(
                    f"prospect batch not found: {run.prospect_batch_id}"
                )
            jobs = await uow.prospect_jobs.list_for_batch(batch.id)
            duplicate_counts = _duplicate_counts_by_company(batch.companies)
            reports: list[CalibrationCompanyReport] = []
            for item in batch.companies:
                company = await uow.companies.get_by_id(item.company_id)
                research = (
                    await uow.research_runs.get_by_id(item.research_id)
                    if item.research_id is not None
                    else None
                )
                opportunity = (
                    await uow.opportunities.get_by_id(item.opportunity_id)
                    if item.opportunity_id is not None
                    else None
                )
                contact = (
                    await uow.contacts.get_by_id(item.selected_contact_id)
                    if item.selected_contact_id is not None
                    else None
                )
                outreach = (
                    await uow.outreaches.get_by_id(item.outreach_id)
                    if item.outreach_id is not None
                    else None
                )
                reports.append(
                    _company_report(
                        item=item,
                        research=research,
                        company=company,
                        opportunity=opportunity,
                        contact=contact,
                        outreach=outreach,
                        jobs=jobs,
                        duplicate_entity_count=duplicate_counts.get(item.company_id, 0),
                        evaluation=run.evaluation_for(item.company_id),
                        generated_at=generated_at,
                    )
                )

        companies = tuple(reports)
        providers = _provider_metrics(run, companies)
        summary = _summary(companies)
        truth_checks = _truth_checks(
            companies,
            duplicate_entity_count=_duplicate_entity_count(batch.companies),
        )
        status = (
            "running"
            if any(item.final_status in {"queued", "running"} for item in companies)
            else "needs_review"
            if any(item.final_status == "needs_review" for item in companies)
            else batch.status.value
        )
        return CalibrationReport(
            calibration_id=run.id,
            discovery_task_id=run.discovery_task_id,
            prospect_batch_id=run.prospect_batch_id,
            status=status,
            sample_source="manual_csv",
            sample_reality_status="user_supplied_unverified",
            created_at=run.created_at,
            updated_at=run.updated_at,
            generated_at=generated_at,
            providers=providers,
            summary=summary,
            truth_checks=truth_checks,
            companies=companies,
        )


def _company_report(
    *,
    item: ProspectBatchCompany,
    research: ResearchRun | None,
    company: object | None,
    opportunity: object | None,
    contact: object | None,
    outreach: object | None,
    jobs: list[ProspectJob],
    duplicate_entity_count: int,
    evaluation: CalibrationEvaluation | None,
    generated_at: datetime,
) -> CalibrationCompanyReport:
    # Imports remain local so this read-model module exposes no persistence or
    # provider types while retaining precise static types after the UoW loads.
    from app.domain.company import Company
    from app.domain.contact import Contact
    from app.domain.opportunity import Opportunity
    from app.domain.outreach import Outreach

    typed_company = company if isinstance(company, Company) else None
    typed_opportunity = opportunity if isinstance(opportunity, Opportunity) else None
    typed_contact = contact if isinstance(contact, Contact) else None
    typed_outreach = outreach if isinstance(outreach, Outreach) else None

    promotions = {p.claim_position: p for p in research.promotions} if research else {}
    accepted_count = sum(
        p.decision is PromotionDecision.ACCEPTED for p in promotions.values()
    )
    edited_count = sum(p.decision is PromotionDecision.EDITED for p in promotions.values())
    rejected_count = sum(
        p.decision is PromotionDecision.REJECTED for p in promotions.values()
    )
    pending_count = (
        sum(claim.position not in promotions for claim in research.claims)
        if research
        else 0
    )
    research_metrics = ResearchMetrics(
        request_succeeded=(
            research is not None
            and research.pages_fetched > 0
            and research.status
            in {ResearchRunStatus.COMPLETED, ResearchRunStatus.PARTIAL}
        ),
        pages_fetched=research.pages_fetched if research else 0,
        duration_ms=(
            _duration_ms(research.started_at, research.completed_at)
            if research
            else None
        ),
        new_claim_count=research.claims_validated if research else 0,
        accepted_count=accepted_count,
        edited_count=edited_count,
        rejected_count=rejected_count,
        pending_count=pending_count,
        claims_without_source_count=(
            sum(research.page_at(claim.source_page_position) is None for claim in research.claims)
            if research
            else 0
        ),
        failure_reason=(
            research.failure_code.value
            if research and research.failure_code is not None
            else item.error_summary
            if item.error_code in {"RESEARCH_FAILED", "RESEARCH_INCOMPLETE"}
            else None
        ),
    )

    latest = (
        typed_opportunity.history[-1]
        if typed_opportunity and typed_opportunity.history
        else None
    )
    positive: list[str] = []
    deductions: list[str] = []
    limiting: list[str] = []
    if latest and latest.score_breakdown:
        for dimension in latest.score_breakdown.dimensions:
            if dimension.status is DimensionStatus.ASSESSED and dimension.earned_score > 0:
                positive.extend(dimension.reasons)
            elif dimension.status in {
                DimensionStatus.UNKNOWN,
                DimensionStatus.INSUFFICIENT_EVIDENCE,
            }:
                limiting.extend(dimension.reasons)
    if latest:
        deductions.extend(reason for reason in latest.reasons if "hard gate" in reason.lower())
    trusted_evidence_count = (
        sum(
            any(source.source in {"importyeti", "import_evidence"} for source in evidence.sources)
            for evidence in latest.evidence
        )
        if latest
        else 0
    )
    opportunity_metrics = OpportunityMetrics(
        generated=latest is not None,
        score=latest.new_score.value if latest else item.score,
        qualification_decision=(
            latest.qualification_decision.value
            if latest and latest.qualification_decision
            else item.qualification_decision
        ),
        major_positive_reasons=tuple(positive[:3]),
        major_deduction_reasons=tuple(deductions[:3]),
        limiting_reasons=tuple(limiting[:3]),
        trusted_evidence_count=trusted_evidence_count,
        stopped_for_insufficient_evidence=item.error_code
        in {"INSUFFICIENT_TRUSTED_EVIDENCE", "OPPORTUNITY_NOT_QUALIFIED"},
    )

    email = None
    phone = None
    manually_confirmed = False
    title_or_department = None
    if typed_contact is not None:
        title_or_department = (
            typed_contact.title.raw if typed_contact.title else typed_contact.department.value
        )
        for channel in typed_contact.usable_channels:
            if channel.channel_type is ContactChannelType.EMAIL and email is None:
                email = channel.display_value
            if channel.channel_type is ContactChannelType.PHONE and phone is None:
                phone = channel.display_value
            if channel.verification_status is ContactVerificationStatus.MANUALLY_VERIFIED:
                manually_confirmed = True
    contact_metrics = ContactMetrics(
        personal_contact_found=item.contact_type is ProspectContactType.PERSONAL,
        department_contact_found=item.contact_type is ProspectContactType.DEPARTMENT,
        contact_type=item.contact_type.value if item.contact_type else None,
        name=typed_contact.name.value if typed_contact else item.contact_name,
        title_or_department=title_or_department,
        email=email or item.contact_email,
        phone=phone,
        source_url=item.contact_source_url,
        manually_confirmed=manually_confirmed,
        contact_not_found_reason=(
            item.error_summary
            if item.error_code in {"CONTACT_NOT_FOUND", "CONTACT_UNUSABLE"}
            else None
        ),
    )

    draft = None
    if typed_outreach is not None and item.draft_version is not None:
        draft = next(
            (value for value in typed_outreach.drafts if value.version == item.draft_version),
            None,
        )
    company_sources = (
        {(source.source, source.reference) for source in typed_company.sources}
        if typed_company
        else set()
    )
    facts = tuple(
        DraftFactReport(
            claim=evidence.claim,
            source_urls=tuple(source.reference for source in evidence.sources),
            traceable_to_company_evidence=all(
                (source.source, source.reference) in company_sources
                for source in evidence.sources
            ),
        )
        for evidence in latest.evidence
    ) if latest else ()
    unreviewed_claims, rejected_claims = _blocked_claim_text(research)
    searchable = (
        tuple(typed_company.signals) if typed_company else (),
        tuple(fact.claim for fact in facts),
        (draft.body,) if draft else (),
    )
    contains_unreviewed = _contains_any(searchable, unreviewed_claims)
    contains_rejected = _contains_any(searchable, rejected_claims)
    draft_metrics = DraftMetrics(
        generated=draft is not None,
        not_generated_reason=None if draft else item.error_summary,
        contact_type=item.contact_type.value if item.contact_type else None,
        fact_count=len(facts),
        facts=facts,
        all_facts_traceable=bool(facts)
        and all(fact.traceable_to_company_evidence for fact in facts),
        contains_unreviewed_claim=contains_unreviewed,
        contains_rejected_claim=contains_rejected,
        awaiting_human_review=(
            draft is not None and draft.approval_status is EmailDraftStatus.GENERATED
        ),
        explicitly_not_sent=(
            typed_outreach is None
            or (
                typed_outreach.sent_version is None
                and typed_outreach.status not in {
                    OutreachStatus.SENT,
                    OutreachStatus.REPLIED,
                    OutreachStatus.WON,
                }
            )
        ),
    )

    earliest_job = jobs[0] if jobs else None
    stage_durations = Counter[str]()
    for timing in item.stage_timings:
        end = timing.completed_at or generated_at
        stage_durations[timing.stage.value] += _duration_ms(timing.started_at, end) or 0
    worker_metrics = WorkerMetrics(
        queue_wait_ms=(
            _duration_ms(earliest_job.created_at, earliest_job.started_at)
            if earliest_job
            else None
        ),
        total_duration_ms=(
            _duration_ms(item.started_at, item.completed_at or generated_at)
            if item.started_at
            else None
        ),
        stage_durations_ms=dict(stage_durations),
        attempt_count=sum(job.attempt_count for job in jobs),
        recovery_count=sum(job.recovery_count for job in jobs),
        lease_expired=any(job.recovery_count > 0 for job in jobs),
        duplicate_entity_count=duplicate_entity_count,
    )

    evaluation_view = (
        CalibrationEvaluationView(
            research_accuracy=evaluation.research_accuracy,
            opportunity_reasonableness=evaluation.opportunity_reasonableness,
            contact_usability=evaluation.contact_usability,
            draft_personalization=evaluation.draft_personalization,
            draft_professionalism=evaluation.draft_professionalism,
            ready_for_real_outreach=evaluation.ready_for_real_outreach,
            reviewer_name=evaluation.reviewer_name,
            notes=evaluation.notes,
            reviewed_at=evaluation.reviewed_at,
        )
        if evaluation
        else None
    )
    return CalibrationCompanyReport(
        company_id=item.company_id,
        company_name=item.company_name,
        final_status=item.status.value,
        error_code=item.error_code,
        error_summary=item.error_summary,
        research=research_metrics,
        opportunity=opportunity_metrics,
        contact=contact_metrics,
        draft=draft_metrics,
        worker=worker_metrics,
        evaluation=evaluation_view,
    )


def _provider_metrics(
    run: CalibrationRun, companies: tuple[CalibrationCompanyReport, ...]
) -> CalibrationProviderMetrics:
    research_calls = (
        sum(item.research.duration_ms is not None for item in companies)
        if run.research_provider_mode is ResearchProviderMode.REAL
        else 0
    )
    draft_calls = (
        sum(item.draft.generated for item in companies)
        if run.draft_provider_mode is DraftProviderMode.REAL
        else 0
    )
    provider_duration_ms = sum(item.research.duration_ms or 0 for item in companies)
    provider_duration_ms += sum(
        item.worker.stage_durations_ms.get("generating_draft", 0) for item in companies
    )
    paid_request_count = research_calls + draft_calls
    return CalibrationProviderMetrics(
        website_fetch_mode=run.website_fetch_mode.value,
        research_provider_mode=run.research_provider_mode.value,
        draft_provider_mode=run.draft_provider_mode.value,
        contact_source_mode=run.contact_source_mode.value,
        paid_request_count=paid_request_count,
        research_provider_call_count=research_calls,
        draft_provider_call_count=draft_calls,
        provider_duration_ms=provider_duration_ms,
        token_usage_total=0 if paid_request_count == 0 else None,
    )


def _summary(companies: tuple[CalibrationCompanyReport, ...]) -> CalibrationSummary:
    count = len(companies)
    evaluations = [item.evaluation for item in companies if item.evaluation is not None]
    durations = [
        item.worker.total_duration_ms
        for item in companies
        if item.worker.total_duration_ms is not None
    ]
    research_success = sum(item.research.request_succeeded for item in companies)
    opportunities = sum(item.opportunity.generated for item in companies)
    personal = sum(item.contact.personal_contact_found for item in companies)
    department = sum(item.contact.department_contact_found for item in companies)
    drafts = sum(item.draft.generated for item in companies)
    return CalibrationSummary(
        sample_count=count,
        website_research_success_count=research_success,
        website_research_success_rate=_rate(research_success, count),
        evidence_review_company_count=sum(
            item.research.new_claim_count > 0 for item in companies
        ),
        evidence_accepted_count=sum(item.research.accepted_count for item in companies),
        evidence_rejected_count=sum(item.research.rejected_count for item in companies),
        opportunity_generated_count=opportunities,
        opportunity_generation_rate=_rate(opportunities, count),
        qualified_count=sum(
            item.opportunity.qualification_decision == "qualified" for item in companies
        ),
        personal_contact_count=personal,
        personal_contact_coverage_rate=_rate(personal, count),
        department_contact_count=department,
        department_contact_coverage_rate=_rate(department, count),
        draft_generated_count=drafts,
        draft_generation_rate=_rate(drafts, count),
        ready_for_real_outreach_count=sum(
            bool(item.evaluation and item.evaluation.ready_for_real_outreach)
            for item in companies
        ),
        evaluated_company_count=len(evaluations),
        worker_recovery_count=max(
            (item.worker.recovery_count for item in companies), default=0
        ),
        average_processing_duration_ms=(
            round(sum(durations) / len(durations)) if durations else None
        ),
        average_research_accuracy=_average(
            [item.research_accuracy for item in evaluations]
        ),
        average_opportunity_reasonableness=_average(
            [item.opportunity_reasonableness for item in evaluations]
        ),
        average_contact_usability=_average(
            [item.contact_usability for item in evaluations]
        ),
        average_draft_personalization=_average(
            [item.draft_personalization for item in evaluations]
        ),
        average_draft_professionalism=_average(
            [item.draft_professionalism for item in evaluations]
        ),
    )


def _truth_checks(
    companies: tuple[CalibrationCompanyReport, ...],
    *,
    duplicate_entity_count: int = 0,
) -> CalibrationTruthChecks:
    invalid_email_count = 0
    for item in companies:
        if item.contact.email:
            try:
                EmailAddress(item.contact.email)
            except DomainError:
                invalid_email_count += 1
    return CalibrationTruthChecks(
        fabricated_contact_count=sum(
            bool(item.contact.name or item.contact.email)
            and (not item.contact.source_url or item.contact.contact_type is None)
            for item in companies
        ),
        unreviewed_fact_in_draft_count=sum(
            item.draft.contains_unreviewed_claim for item in companies
        ),
        rejected_claim_in_score_or_draft_count=sum(
            item.draft.contains_rejected_claim for item in companies
        ),
        pending_claim_bypassed_count=sum(
            item.research.pending_count > 0
            and (item.opportunity.generated or item.draft.generated)
            for item in companies
        ),
        draft_marked_sent_count=sum(
            item.draft.generated and not item.draft.explicitly_not_sent
            for item in companies
        ),
        duplicate_entity_count=duplicate_entity_count,
        invalid_email_contact_count=invalid_email_count,
        website_failure_mislabeled_company_missing_count=sum(
            item.error_code in {"RESEARCH_FAILED", "RESEARCH_INCOMPLETE"}
            and "company" in (item.error_summary or "").lower()
            and "not found" in (item.error_summary or "").lower()
            for item in companies
        ),
    )


def _duplicate_entity_count(items: tuple[ProspectBatchCompany, ...]) -> int:
    opportunity_ids = [item.opportunity_id for item in items if item.opportunity_id]
    contact_ids = [item.selected_contact_id for item in items if item.selected_contact_id]
    outreach_drafts = [
        (item.outreach_id, item.draft_version)
        for item in items
        if item.outreach_id is not None and item.draft_version is not None
    ]
    return sum(
        count - 1
        for values in (opportunity_ids, contact_ids, outreach_drafts)
        for count in Counter(values).values()
        if count > 1
    )


def _duplicate_counts_by_company(
    items: tuple[ProspectBatchCompany, ...],
) -> dict[UUID, int]:
    opportunity_counts = Counter(
        item.opportunity_id for item in items if item.opportunity_id is not None
    )
    contact_counts = Counter(
        item.selected_contact_id for item in items if item.selected_contact_id is not None
    )
    draft_counts = Counter(
        (item.outreach_id, item.draft_version)
        for item in items
        if item.outreach_id is not None and item.draft_version is not None
    )
    return {
        item.company_id: sum(
            (
                (
                    item.opportunity_id is not None
                    and opportunity_counts[item.opportunity_id] > 1
                ),
                item.selected_contact_id is not None
                and contact_counts[item.selected_contact_id] > 1,
                item.outreach_id is not None
                and item.draft_version is not None
                and draft_counts[(item.outreach_id, item.draft_version)] > 1,
            )
        )
        for item in items
    }


def _blocked_claim_text(run: ResearchRun | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if run is None:
        return (), ()
    promotions = {item.claim_position: item for item in run.promotions}
    pending: list[str] = []
    rejected: list[str] = []
    for claim in run.claims:
        rendered = f"{claim.kind}: {claim.detail}"
        promotion = promotions.get(claim.position)
        if promotion is None:
            pending.append(rendered)
            pending.append(claim.detail)
        elif promotion.decision is PromotionDecision.REJECTED:
            rejected.append(rendered)
            rejected.append(claim.detail)
    return tuple(pending), tuple(rejected)


def _contains_any(groups: tuple[tuple[str, ...], ...], needles: tuple[str, ...]) -> bool:
    return any(
        needle and needle in value
        for group in groups
        for value in group
        for needle in needles
    )


def _duration_ms(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    return max(0, round((end - start).total_seconds() * 1000))


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _average(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None
