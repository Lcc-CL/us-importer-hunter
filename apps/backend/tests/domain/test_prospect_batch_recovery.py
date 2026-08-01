"""Batch business state remains distinct from worker execution recovery."""

from uuid import uuid4

from app.domain.prospect_batch import (
    ProspectBatch,
    ProspectBatchCompanyStatus,
    ProspectBatchStage,
    ProspectBatchStatus,
)


def make_batch() -> ProspectBatch:
    return ProspectBatch.create(
        discovery_task_id=uuid4(),
        requested_count=2,
        companies=((uuid4(), "Running Co"), (uuid4(), "Review Co")),
    )


def test_stale_recovery_requeues_running_but_never_restarts_evidence_review() -> None:
    batch = make_batch()
    running, review = batch.companies
    batch.start()
    batch.replace_company(running.move_to(ProspectBatchStage.RESEARCHING))
    batch.replace_company(
        review.move_to(ProspectBatchStage.RESEARCHING).await_evidence_review(
            blocking_claim_count=2
        )
    )

    batch.recover_stale_execution()

    recovered_running = batch.company(running.company_id)
    recovered_review = batch.company(review.company_id)
    assert batch.status is ProspectBatchStatus.PENDING
    assert recovered_running.status is ProspectBatchCompanyStatus.QUEUED
    assert recovered_running.current_stage is ProspectBatchStage.QUEUED
    assert recovered_review.status is ProspectBatchCompanyStatus.NEEDS_REVIEW
    assert recovered_review.current_stage is ProspectBatchStage.AWAITING_EVIDENCE_REVIEW


def test_exhausted_worker_attempts_fail_only_active_companies() -> None:
    batch = make_batch()
    running, review = batch.companies
    batch.start()
    batch.replace_company(running.move_to(ProspectBatchStage.SCORING))
    batch.replace_company(
        review.move_to(ProspectBatchStage.RESEARCHING).await_evidence_review(
            blocking_claim_count=1
        )
    )

    batch.fail_active_execution(
        error_code="WORKER_LEASE_EXPIRED",
        error_summary="retry limit exhausted",
    )

    assert batch.status is ProspectBatchStatus.PARTIAL_FAILED
    assert batch.company(running.company_id).status is ProspectBatchCompanyStatus.FAILED
    assert (
        batch.company(review.company_id).current_stage
        is ProspectBatchStage.AWAITING_EVIDENCE_REVIEW
    )
