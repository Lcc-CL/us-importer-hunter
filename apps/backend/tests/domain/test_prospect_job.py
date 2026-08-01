"""Domain tests for background prospect-job lease and recovery semantics."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.exceptions import InvalidStateTransition
from app.domain.prospect_job import ProspectJob, ProspectJobStatus

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
TTL = timedelta(seconds=120)


def make_job(*, max_attempts: int = 3) -> ProspectJob:
    return ProspectJob.create(
        batch_id=uuid4(),
        business_key="a" * 64,
        request_key_hash=None,
        sender=None,
        max_attempts=max_attempts,
        now=NOW,
    )


def test_lease_start_heartbeat_and_complete_are_auditable() -> None:
    leased = make_job().lease(owner="worker-a", lease_ttl=TTL, now=NOW)
    assert leased.status is ProspectJobStatus.LEASED
    assert leased.attempt_count == 1
    assert leased.lease_expires_at == NOW + TTL

    running = leased.start(owner="worker-a", now=NOW + timedelta(seconds=1))
    heartbeat = running.heartbeat(
        owner="worker-a",
        lease_ttl=TTL,
        now=NOW + timedelta(seconds=30),
    )
    assert heartbeat.status is ProspectJobStatus.RUNNING
    assert heartbeat.lease_expires_at == NOW + timedelta(seconds=150)

    completed = heartbeat.complete(owner="worker-a", now=NOW + timedelta(seconds=40))
    assert completed.status is ProspectJobStatus.COMPLETED
    assert completed.lease_owner is None
    assert completed.complete(owner="worker-a") is completed


def test_only_current_lease_owner_can_mutate_running_job() -> None:
    leased = make_job().lease(owner="worker-a", lease_ttl=TTL, now=NOW)
    with pytest.raises(InvalidStateTransition, match="owner"):
        leased.start(owner="worker-b")


def test_technical_error_requeues_then_fails_at_max_attempts() -> None:
    first = make_job(max_attempts=2).lease(owner="worker-a", lease_ttl=TTL, now=NOW)
    pending = first.retry_after_error(
        owner="worker-a",
        error_code="DATABASE_UNAVAILABLE",
        error_summary="DatabaseError",
        delay=timedelta(seconds=5),
        now=NOW + timedelta(seconds=1),
    )
    assert pending.status is ProspectJobStatus.PENDING
    assert pending.available_at == NOW + timedelta(seconds=6)

    second = pending.lease(
        owner="worker-b",
        lease_ttl=TTL,
        now=NOW + timedelta(seconds=6),
    )
    failed = second.retry_after_error(
        owner="worker-b",
        error_code="DATABASE_UNAVAILABLE",
        error_summary="DatabaseError",
        delay=timedelta(seconds=5),
        now=NOW + timedelta(seconds=7),
    )
    assert failed.status is ProspectJobStatus.FAILED
    assert failed.attempt_count == 2


def test_stale_recovery_requeues_or_fails_without_preserving_owner() -> None:
    leased = make_job(max_attempts=2).lease(owner="worker-a", lease_ttl=TTL, now=NOW)
    recovered = leased.recover_stale(now=NOW + TTL + timedelta(seconds=1))
    assert recovered.status is ProspectJobStatus.PENDING
    assert recovered.recovery_count == 1
    assert recovered.lease_owner is None

    second = recovered.lease(
        owner="worker-b",
        lease_ttl=TTL,
        now=NOW + TTL + timedelta(seconds=1),
    )
    exhausted = second.recover_stale(now=NOW + 2 * TTL + timedelta(seconds=2))
    assert exhausted.status is ProspectJobStatus.FAILED
    assert exhausted.recovery_count == 2


def test_stale_terminal_batch_can_reconcile_job_completed() -> None:
    leased = make_job().lease(owner="worker-a", lease_ttl=TTL, now=NOW)
    completed = leased.reconcile_completed_after_recovery(
        now=NOW + TTL + timedelta(seconds=1)
    )
    assert completed.status is ProspectJobStatus.COMPLETED
    assert completed.recovery_count == 1
