"""DiscoveryRun aggregate (Discovery context): one supervised discovery pass.

Boundary rule (ADR-0018): Discovery produces domain events only. It never
creates Company or Opportunity aggregates and never scores anything —
the Company context consumes CompanyDiscovered claims downstream.

Counting semantics: one source query that succeeds may yield several
claims — `succeeded`/`failed` count queries, `discovered` counts claims.
"""

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.discovery.values import DiscoveryResult, DiscoveryStats
from app.domain.events import (
    CompanyDiscovered,
    DiscoveryCompleted,
    DiscoveryFailed,
    DomainEvent,
)
from app.domain.exceptions import DomainError, InvalidStateTransition


class DiscoveryRunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


TERMINAL_RUN_STATUSES = frozenset({DiscoveryRunStatus.COMPLETED, DiscoveryRunStatus.FAILED})


class DiscoveryRun:
    """Aggregate root for one discovery pass over the user's targeting criteria."""

    def __init__(
        self,
        *,
        id: UUID,
        criteria: str,
        user_id: UUID,
        created_at: datetime,
    ) -> None:
        self._id = id
        self._criteria = criteria
        self._user_id = user_id
        self._created_at = created_at
        self._status = DiscoveryRunStatus.CREATED
        self._started_at: datetime | None = None
        self._finished_at: datetime | None = None
        self._error: str | None = None
        self._discovered = 0
        self._succeeded = 0
        self._failed = 0
        self._results: list[DiscoveryResult] = []
        self._events: list[DomainEvent] = []

    # -- construction -------------------------------------------------

    @classmethod
    def create(cls, criteria: str, user_id: UUID) -> "DiscoveryRun":
        if not criteria.strip():
            raise DomainError("discovery run requires targeting criteria")
        return cls(id=uuid4(), criteria=criteria.strip(), user_id=user_id, created_at=utcnow())

    # -- guards -------------------------------------------------------

    def _ensure_running(self, operation: str) -> None:
        if self._status is not DiscoveryRunStatus.RUNNING:
            raise InvalidStateTransition(
                f"cannot {operation} a {self._status.value} discovery run"
            )

    # -- behaviors ----------------------------------------------------

    def start(self) -> None:
        if self._status is not DiscoveryRunStatus.CREATED:
            raise InvalidStateTransition(f"cannot start a {self._status.value} discovery run")
        self._status = DiscoveryRunStatus.RUNNING
        self._started_at = utcnow()

    def record_success(self, results: Sequence[DiscoveryResult]) -> None:
        """One source query succeeded, yielding zero or more claims."""
        self._ensure_running("record results on")
        self._succeeded += 1
        for result in results:
            self._results.append(result)
            self._discovered += 1
            self._events.append(CompanyDiscovered(run_id=self._id, result=result))

    def record_failure(self, reason: str) -> None:
        """One source query failed; the run itself continues."""
        self._ensure_running("record a failure on")
        if not reason.strip():
            raise DomainError("a failure record requires a reason")
        self._failed += 1

    def complete(self) -> None:
        self._ensure_running("complete")
        self._status = DiscoveryRunStatus.COMPLETED
        self._finished_at = utcnow()
        self._events.append(DiscoveryCompleted(run_id=self._id, stats=self.stats))

    def fail(self, error: str) -> None:
        """The run itself broke (as opposed to a single query failing)."""
        self._ensure_running("fail")
        if not error.strip():
            raise DomainError("failing a run requires an error description")
        self._status = DiscoveryRunStatus.FAILED
        self._error = error.strip()
        self._finished_at = utcnow()
        self._events.append(DiscoveryFailed(run_id=self._id, error=self._error, stats=self.stats))

    # -- events -------------------------------------------------------

    def drain_events(self) -> tuple[DomainEvent, ...]:
        events = tuple(self._events)
        self._events.clear()
        return events

    # -- read-only state ----------------------------------------------

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def criteria(self) -> str:
        return self._criteria

    @property
    def user_id(self) -> UUID:
        return self._user_id

    @property
    def status(self) -> DiscoveryRunStatus:
        return self._status

    @property
    def started_at(self) -> datetime | None:
        return self._started_at

    @property
    def finished_at(self) -> datetime | None:
        return self._finished_at

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def stats(self) -> DiscoveryStats:
        return DiscoveryStats(
            discovered=self._discovered, succeeded=self._succeeded, failed=self._failed
        )

    @property
    def results(self) -> tuple[DiscoveryResult, ...]:
        return tuple(self._results)

    @property
    def created_at(self) -> datetime:
        return self._created_at
