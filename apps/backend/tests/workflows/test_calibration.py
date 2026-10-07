"""D4a calibration orchestration and report calculations."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.domain.calibration import (
    CalibrationRun,
    DraftProviderMode,
    ResearchProviderMode,
    WebsiteFetchMode,
)
from app.domain.prospect_batch import ProspectBatch
from app.domain.prospect_job import ProspectJob
from app.domain.repositories import CalibrationUnitOfWork
from app.shared.exceptions import InvalidInputError
from app.workflows.calibration import (
    CalibrationCompanyReport,
    CalibrationCreateCommand,
    CalibrationEvaluationView,
    ContactMetrics,
    CreateCalibrationRunWorkflow,
    DraftFactReport,
    DraftMetrics,
    OpportunityMetrics,
    ResearchMetrics,
    WorkerMetrics,
)
from app.workflows.calibration.workflow import _summary, _truth_checks
from app.workflows.prospect_batch import (
    CreateProspectBatchCommand,
    ProspectBatchSubmission,
    ProspectBatchSubmissionWorkflow,
)

NOW = datetime(2026, 8, 1, tzinfo=UTC)


class FakeCalibrationRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, CalibrationRun] = {}

    async def get_by_id(self, calibration_id: UUID) -> CalibrationRun | None:
        return self.items.get(calibration_id)

    async def get_by_batch_id(self, batch_id: UUID) -> CalibrationRun | None:
        return next(
            (run for run in self.items.values() if run.prospect_batch_id == batch_id),
            None,
        )

    async def add(self, run: CalibrationRun) -> None:
        self.items[run.id] = run

    async def save(self, run: CalibrationRun) -> None:
        self.items[run.id] = run


class FakeCalibrationUnitOfWork:
    def __init__(self, calibrations: FakeCalibrationRepository) -> None:
        self.calibrations = calibrations

    async def __aenter__(self) -> "FakeCalibrationUnitOfWork":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class FakeBatchSubmissionWorkflow:
    def __init__(self) -> None:
        self.calls = 0
        self._submission: ProspectBatchSubmission | None = None

    async def submit(
        self,
        discovery_task_id: UUID,
        command: CreateProspectBatchCommand,
        *,
        idempotency_key: str | None,
    ) -> ProspectBatchSubmission:
        del idempotency_key
        self.calls += 1
        company_ids = command.company_ids
        if self._submission is None:
            batch = ProspectBatch.create(
                discovery_task_id=discovery_task_id,
                requested_count=len(company_ids),
                companies=tuple(
                    (company_id, f"Company {position + 1}")
                    for position, company_id in enumerate(company_ids)
                ),
            )
            job = ProspectJob.create(
                batch_id=batch.id,
                business_key=f"prospect-batch:{batch.id}",
                request_key_hash=None,
                sender=None,
            )
            self._submission = ProspectBatchSubmission(batch=batch, job=job, reused=False)
        return self._submission


def create_workflow(
    *,
    batch_submission: FakeBatchSubmissionWorkflow,
    calibrations: FakeCalibrationRepository,
    research_mode: ResearchProviderMode = ResearchProviderMode.DETERMINISTIC_FAKE,
    draft_mode: DraftProviderMode = DraftProviderMode.DETERMINISTIC_FAKE,
) -> CreateCalibrationRunWorkflow:
    return CreateCalibrationRunWorkflow(
        uow_factory=cast(
            Callable[[], CalibrationUnitOfWork],
            lambda: FakeCalibrationUnitOfWork(calibrations),
        ),
        batch_submission=cast(ProspectBatchSubmissionWorkflow, batch_submission),
        website_fetch_mode=WebsiteFetchMode.FIXTURE,
        research_provider_mode=research_mode,
        draft_provider_mode=draft_mode,
    )


async def test_creation_reuses_the_existing_batch_and_persists_provider_modes() -> None:
    calibrations = FakeCalibrationRepository()
    batches = FakeBatchSubmissionWorkflow()
    workflow = create_workflow(batch_submission=batches, calibrations=calibrations)
    company_ids = tuple(uuid4() for _ in range(3))

    first = await workflow.handle(
        uuid4(),
        CalibrationCreateCommand(company_ids=company_ids),
        idempotency_key="same-click",
    )
    second = await workflow.handle(
        first.run.discovery_task_id,
        CalibrationCreateCommand(company_ids=company_ids),
        idempotency_key="same-click",
    )

    assert first.run.sample_count == 3
    assert first.run.website_fetch_mode is WebsiteFetchMode.FIXTURE
    assert first.run.research_provider_mode is ResearchProviderMode.DETERMINISTIC_FAKE
    assert first.run.draft_provider_mode is DraftProviderMode.DETERMINISTIC_FAKE
    assert second.run.id == first.run.id
    assert second.reused is True


@pytest.mark.parametrize("count", [2, 6])
async def test_creation_rejects_samples_outside_three_to_five(count: int) -> None:
    calibrations = FakeCalibrationRepository()
    batches = FakeBatchSubmissionWorkflow()
    workflow = create_workflow(batch_submission=batches, calibrations=calibrations)

    with pytest.raises(InvalidInputError) as caught:
        await workflow.handle(
            uuid4(),
            CalibrationCreateCommand(company_ids=tuple(uuid4() for _ in range(count))),
            idempotency_key=None,
        )

    assert caught.value.code == "CALIBRATION_SAMPLE_SIZE_INVALID"
    assert batches.calls == 0


@pytest.mark.parametrize(
    ("research_mode", "draft_mode"),
    [
        (ResearchProviderMode.REAL, DraftProviderMode.DETERMINISTIC_FAKE),
        (ResearchProviderMode.DETERMINISTIC_FAKE, DraftProviderMode.REAL),
    ],
)
async def test_real_provider_mode_fails_before_submitting_three_to_five_companies(
    research_mode: ResearchProviderMode,
    draft_mode: DraftProviderMode,
) -> None:
    calibrations = FakeCalibrationRepository()
    batches = FakeBatchSubmissionWorkflow()
    workflow = create_workflow(
        batch_submission=batches,
        calibrations=calibrations,
        research_mode=research_mode,
        draft_mode=draft_mode,
    )

    with pytest.raises(InvalidInputError) as caught:
        await workflow.handle(
            uuid4(),
            CalibrationCreateCommand(company_ids=tuple(uuid4() for _ in range(3))),
            idempotency_key=None,
        )

    assert caught.value.code == "CALIBRATION_REAL_PROVIDER_REQUIRES_CONTROLLED_RUN"
    assert batches.calls == 0


def company_report(
    *,
    company_name: str,
    pending: int = 0,
    opportunity_generated: bool = True,
    contact_type: str | None = "personal",
    contact_email: str | None = "buyer@example.com",
    contact_source_url: str | None = "https://example.com/contact",
    draft_generated: bool = True,
    contains_unreviewed: bool = False,
    contains_rejected: bool = False,
    explicitly_not_sent: bool = True,
    evaluation: CalibrationEvaluationView | None = None,
) -> CalibrationCompanyReport:
    return CalibrationCompanyReport(
        company_id=uuid4(),
        company_name=company_name,
        final_status="completed",
        error_code=None,
        error_summary=None,
        research=ResearchMetrics(
            request_succeeded=True,
            pages_fetched=2,
            duration_ms=100,
            new_claim_count=2,
            accepted_count=1,
            edited_count=0,
            rejected_count=1,
            pending_count=pending,
            claims_without_source_count=0,
            failure_reason=None,
        ),
        opportunity=OpportunityMetrics(
            generated=opportunity_generated,
            score=72.0 if opportunity_generated else None,
            qualification_decision="qualified" if opportunity_generated else None,
            major_positive_reasons=("trusted import evidence",),
            major_deduction_reasons=(),
            limiting_reasons=(),
            trusted_evidence_count=1 if opportunity_generated else 0,
            stopped_for_insufficient_evidence=not opportunity_generated,
        ),
        contact=ContactMetrics(
            personal_contact_found=contact_type == "personal",
            department_contact_found=contact_type == "department",
            contact_type=contact_type,
            name="Buyer" if contact_type else None,
            title_or_department="Procurement" if contact_type else None,
            email=contact_email,
            phone=None,
            source_url=contact_source_url,
            manually_confirmed=False,
            contact_not_found_reason=None if contact_type else "CONTACT_NOT_FOUND",
        ),
        draft=DraftMetrics(
            generated=draft_generated,
            not_generated_reason=None if draft_generated else "no contact",
            contact_type=contact_type,
            fact_count=1 if draft_generated else 0,
            facts=(
                DraftFactReport(
                    claim="import activity confirmed",
                    source_urls=("https://evidence.example/1",),
                    traceable_to_company_evidence=True,
                ),
            )
            if draft_generated
            else (),
            all_facts_traceable=draft_generated,
            contains_unreviewed_claim=contains_unreviewed,
            contains_rejected_claim=contains_rejected,
            awaiting_human_review=draft_generated,
            explicitly_not_sent=explicitly_not_sent,
        ),
        worker=WorkerMetrics(
            queue_wait_ms=10,
            total_duration_ms=500,
            stage_durations_ms={"researching": 100},
            attempt_count=1,
            recovery_count=0,
            lease_expired=False,
            duplicate_entity_count=0,
        ),
        evaluation=evaluation,
    )


def test_summary_and_truth_checks_are_explicit_about_blocked_or_invalid_results() -> None:
    evaluated = CalibrationEvaluationView(
        research_accuracy=4,
        opportunity_reasonableness=3,
        contact_usability=2,
        draft_personalization=5,
        draft_professionalism=4,
        ready_for_real_outreach=True,
        reviewer_name="Reviewer",
        notes=None,
        reviewed_at=NOW,
    )
    reports = (
        company_report(company_name="A", evaluation=evaluated),
        company_report(
            company_name="B",
            pending=1,
            contains_unreviewed=True,
            contains_rejected=True,
            explicitly_not_sent=False,
            contact_email="not-an-email",
            contact_source_url=None,
        ),
        company_report(
            company_name="C",
            opportunity_generated=False,
            contact_type=None,
            contact_email=None,
            contact_source_url=None,
            draft_generated=False,
        ),
    )

    summary = _summary(reports)
    truth = _truth_checks(reports, duplicate_entity_count=2)

    assert summary.sample_count == 3
    assert summary.opportunity_generated_count == 2
    assert summary.personal_contact_count == 2
    assert summary.draft_generated_count == 2
    assert summary.ready_for_real_outreach_count == 1
    assert summary.average_research_accuracy == 4.0
    assert truth.unreviewed_fact_in_draft_count == 1
    assert truth.rejected_claim_in_score_or_draft_count == 1
    assert truth.pending_claim_bypassed_count == 1
    assert truth.draft_marked_sent_count == 1
    assert truth.fabricated_contact_count == 1
    assert truth.invalid_email_contact_count == 1
    assert truth.duplicate_entity_count == 2
