"""Framework-free execution state for background prospect-batch jobs."""

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.exceptions import DomainError, InvalidStateTransition
from app.domain.services import SenderProfile


class ProspectJobStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_JOB_STATUSES = frozenset(
    {
        ProspectJobStatus.PENDING,
        ProspectJobStatus.LEASED,
        ProspectJobStatus.RUNNING,
    }
)


@dataclass(frozen=True)
class ProspectJob:
    id: UUID
    batch_id: UUID
    status: ProspectJobStatus
    business_key: str
    request_key_hash: str | None
    sender: SenderProfile | None
    available_at: datetime
    attempt_count: int
    max_attempts: int
    lease_owner: str | None
    lease_acquired_at: datetime | None
    lease_expires_at: datetime | None
    heartbeat_at: datetime | None
    last_error_code: str | None
    last_error_summary: str | None
    recovery_count: int
    last_recovered_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.business_key.strip():
            raise DomainError("prospect job requires a business key")
        if self.attempt_count < 0:
            raise DomainError("prospect job attempt_count must be nonnegative")
        if self.max_attempts < 1:
            raise DomainError("prospect job max_attempts must be positive")
        if self.recovery_count < 0:
            raise DomainError("prospect job recovery_count must be nonnegative")

    @classmethod
    def create(
        cls,
        *,
        batch_id: UUID,
        business_key: str,
        request_key_hash: str | None,
        sender: SenderProfile | None,
        max_attempts: int = 3,
        now: datetime | None = None,
    ) -> "ProspectJob":
        created_at = now or utcnow()
        return cls(
            id=uuid4(),
            batch_id=batch_id,
            status=ProspectJobStatus.PENDING,
            business_key=business_key.strip(),
            request_key_hash=request_key_hash,
            sender=sender,
            available_at=created_at,
            attempt_count=0,
            max_attempts=max_attempts,
            lease_owner=None,
            lease_acquired_at=None,
            lease_expires_at=None,
            heartbeat_at=None,
            last_error_code=None,
            last_error_summary=None,
            recovery_count=0,
            last_recovered_at=None,
            created_at=created_at,
            started_at=None,
            completed_at=None,
            updated_at=created_at,
        )

    def lease(
        self,
        *,
        owner: str,
        lease_ttl: timedelta,
        now: datetime | None = None,
    ) -> "ProspectJob":
        leased_at = now or utcnow()
        if self.status is not ProspectJobStatus.PENDING:
            raise InvalidStateTransition(f"cannot lease a {self.status.value} prospect job")
        if self.available_at > leased_at:
            raise InvalidStateTransition("prospect job is not available yet")
        if not owner.strip():
            raise DomainError("prospect job lease requires an owner")
        if lease_ttl <= timedelta(0):
            raise DomainError("prospect job lease TTL must be positive")
        return dataclasses.replace(
            self,
            status=ProspectJobStatus.LEASED,
            attempt_count=self.attempt_count + 1,
            lease_owner=owner.strip(),
            lease_acquired_at=leased_at,
            lease_expires_at=leased_at + lease_ttl,
            heartbeat_at=leased_at,
            last_error_code=None,
            last_error_summary=None,
            completed_at=None,
            updated_at=leased_at,
        )

    def start(self, *, owner: str, now: datetime | None = None) -> "ProspectJob":
        started_at = now or utcnow()
        self._require_owner(owner)
        if self.status is not ProspectJobStatus.LEASED:
            raise InvalidStateTransition(f"cannot start a {self.status.value} prospect job")
        return dataclasses.replace(
            self,
            status=ProspectJobStatus.RUNNING,
            started_at=self.started_at or started_at,
            heartbeat_at=started_at,
            updated_at=started_at,
        )

    def heartbeat(
        self,
        *,
        owner: str,
        lease_ttl: timedelta,
        now: datetime | None = None,
    ) -> "ProspectJob":
        heartbeat_at = now or utcnow()
        self._require_owner(owner)
        if self.status not in {ProspectJobStatus.LEASED, ProspectJobStatus.RUNNING}:
            raise InvalidStateTransition(f"cannot heartbeat a {self.status.value} prospect job")
        return dataclasses.replace(
            self,
            heartbeat_at=heartbeat_at,
            lease_expires_at=heartbeat_at + lease_ttl,
            updated_at=heartbeat_at,
        )

    def complete(self, *, owner: str, now: datetime | None = None) -> "ProspectJob":
        completed_at = now or utcnow()
        if self.status is ProspectJobStatus.COMPLETED:
            return self
        self._require_owner(owner)
        if self.status not in {ProspectJobStatus.LEASED, ProspectJobStatus.RUNNING}:
            raise InvalidStateTransition(f"cannot complete a {self.status.value} prospect job")
        return dataclasses.replace(
            self,
            status=ProspectJobStatus.COMPLETED,
            lease_owner=None,
            lease_acquired_at=None,
            lease_expires_at=None,
            heartbeat_at=completed_at,
            completed_at=completed_at,
            updated_at=completed_at,
        )

    def retry_after_error(
        self,
        *,
        owner: str,
        error_code: str,
        error_summary: str,
        delay: timedelta,
        now: datetime | None = None,
    ) -> "ProspectJob":
        failed_at = now or utcnow()
        self._require_owner(owner)
        self._require_error(error_code, error_summary)
        if self.status not in {ProspectJobStatus.LEASED, ProspectJobStatus.RUNNING}:
            raise InvalidStateTransition(f"cannot retry a {self.status.value} prospect job")
        if self.attempt_count >= self.max_attempts:
            return self.fail(
                owner=owner,
                error_code=error_code,
                error_summary=error_summary,
                now=failed_at,
            )
        return dataclasses.replace(
            self,
            status=ProspectJobStatus.PENDING,
            available_at=failed_at + max(delay, timedelta(0)),
            lease_owner=None,
            lease_acquired_at=None,
            lease_expires_at=None,
            heartbeat_at=failed_at,
            last_error_code=error_code.strip(),
            last_error_summary=error_summary.strip(),
            completed_at=None,
            updated_at=failed_at,
        )

    def fail(
        self,
        *,
        owner: str,
        error_code: str,
        error_summary: str,
        now: datetime | None = None,
    ) -> "ProspectJob":
        failed_at = now or utcnow()
        self._require_owner(owner)
        self._require_error(error_code, error_summary)
        if self.status not in {ProspectJobStatus.LEASED, ProspectJobStatus.RUNNING}:
            raise InvalidStateTransition(f"cannot fail a {self.status.value} prospect job")
        return dataclasses.replace(
            self,
            status=ProspectJobStatus.FAILED,
            lease_owner=None,
            lease_acquired_at=None,
            lease_expires_at=None,
            heartbeat_at=failed_at,
            last_error_code=error_code.strip(),
            last_error_summary=error_summary.strip(),
            completed_at=failed_at,
            updated_at=failed_at,
        )

    def recover_stale(self, *, now: datetime | None = None) -> "ProspectJob":
        recovered_at = now or utcnow()
        if self.status not in {ProspectJobStatus.LEASED, ProspectJobStatus.RUNNING}:
            raise InvalidStateTransition(f"cannot recover a {self.status.value} prospect job")
        if self.lease_expires_at is None or self.lease_expires_at >= recovered_at:
            raise InvalidStateTransition("prospect job lease has not expired")
        next_status = (
            ProspectJobStatus.FAILED
            if self.attempt_count >= self.max_attempts
            else ProspectJobStatus.PENDING
        )
        return dataclasses.replace(
            self,
            status=next_status,
            available_at=recovered_at,
            lease_owner=None,
            lease_acquired_at=None,
            lease_expires_at=None,
            heartbeat_at=recovered_at,
            last_error_code="WORKER_LEASE_EXPIRED",
            last_error_summary="worker lease expired before the execution completed",
            recovery_count=self.recovery_count + 1,
            last_recovered_at=recovered_at,
            completed_at=recovered_at if next_status is ProspectJobStatus.FAILED else None,
            updated_at=recovered_at,
        )

    def reconcile_completed_after_recovery(
        self, *, now: datetime | None = None
    ) -> "ProspectJob":
        recovered_at = now or utcnow()
        if self.status not in {ProspectJobStatus.LEASED, ProspectJobStatus.RUNNING}:
            raise InvalidStateTransition(f"cannot reconcile a {self.status.value} prospect job")
        if self.lease_expires_at is None or self.lease_expires_at >= recovered_at:
            raise InvalidStateTransition("prospect job lease has not expired")
        return dataclasses.replace(
            self,
            status=ProspectJobStatus.COMPLETED,
            lease_owner=None,
            lease_acquired_at=None,
            lease_expires_at=None,
            heartbeat_at=recovered_at,
            recovery_count=self.recovery_count + 1,
            last_recovered_at=recovered_at,
            completed_at=recovered_at,
            updated_at=recovered_at,
        )

    def _require_owner(self, owner: str) -> None:
        if self.lease_owner != owner.strip():
            raise InvalidStateTransition("prospect job lease owner does not match")

    @staticmethod
    def _require_error(error_code: str, error_summary: str) -> None:
        if not error_code.strip() or not error_summary.strip():
            raise DomainError("prospect job error requires a code and summary")
