"""D5b1 import processing lease, retry and stale recovery semantics."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.import_resolution import ImportJobStatus, ImportProcessingJob

NOW = datetime(2026, 8, 2, tzinfo=UTC)
TTL = timedelta(seconds=120)


def make_job(*, max_attempts: int = 3) -> ImportProcessingJob:
    return ImportProcessingJob.create(
        import_session_id=uuid4(),
        max_attempts=max_attempts,
        now=NOW,
    )


def test_lease_heartbeat_complete() -> None:
    leased = make_job().lease(owner="worker-a", lease_ttl=TTL, now=NOW)
    assert leased.status is ImportJobStatus.LEASED
    running = leased.start(owner="worker-a", now=NOW + timedelta(seconds=1))
    heartbeat = running.heartbeat(
        owner="worker-a",
        lease_ttl=TTL,
        now=NOW + timedelta(seconds=30),
    )
    assert heartbeat.lease_expires_at == NOW + timedelta(seconds=150)
    assert heartbeat.complete(owner="worker-a").status is ImportJobStatus.COMPLETED


def test_retry_and_stale_recovery_exhaust_attempts() -> None:
    first = make_job(max_attempts=2).lease(owner="worker-a", lease_ttl=TTL, now=NOW)
    pending = first.retry_after_error(
        owner="worker-a",
        error_code="ROW_FAILURE",
        error_summary="synthetic",
        delay=timedelta(0),
        now=NOW + timedelta(seconds=1),
    )
    assert pending.status is ImportJobStatus.PENDING
    second = pending.lease(
        owner="worker-b",
        lease_ttl=TTL,
        now=NOW + timedelta(seconds=2),
    )
    failed = second.recover_stale(now=NOW + timedelta(seconds=123))
    assert failed.status is ImportJobStatus.FAILED
    assert failed.recovery_count == 1
    assert failed.last_error_code == "WORKER_LEASE_EXPIRED"
