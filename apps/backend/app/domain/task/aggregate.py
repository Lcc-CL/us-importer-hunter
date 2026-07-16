"""Task aggregate (Execution context): a supervised unit of pipeline work.

Execution state only — never business judgment (ADR-0015). Invariants:
- Completed tasks cannot restart.
- Retries cannot exceed the configured limit.
- Running requires started_at; completed requires finished_at.
- An idempotency key prevents duplicate active tasks.
"""

from collections.abc import Collection
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.events import DomainEvent, TaskCompleted, TaskFailed, TaskStarted
from app.domain.exceptions import (
    DomainError,
    DuplicateOperation,
    InvalidStateTransition,
)
from app.domain.values import IdempotencyKey

DEFAULT_MAX_RETRIES = 3


class TaskStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Task:
    """Aggregate root for one supervised run."""

    def __init__(
        self,
        *,
        id: UUID,
        goal: str,
        idempotency_key: IdempotencyKey,
        max_retries: int,
        created_at: datetime,
    ) -> None:
        self._id = id
        self._goal = goal
        self._idempotency_key = idempotency_key
        self._max_retries = max_retries
        self._created_at = created_at
        self._status = TaskStatus.CREATED
        self._attempts = 0
        self._started_at: datetime | None = None
        self._finished_at: datetime | None = None
        self._error: str | None = None
        self._events: list[DomainEvent] = []

    # -- construction -------------------------------------------------

    @classmethod
    def create(
        cls,
        goal: str,
        idempotency_key: IdempotencyKey,
        *,
        active_keys: Collection[IdempotencyKey] = (),
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> "Task":
        """`active_keys` are the keys of currently active tasks (caller-supplied)."""
        if not goal.strip():
            raise DomainError("task requires a goal")
        if max_retries < 0:
            raise DomainError("max_retries must be >= 0")
        if idempotency_key in active_keys:
            raise DuplicateOperation(
                f"an active task already exists for key {idempotency_key.value!r}"
            )
        return cls(
            id=uuid4(),
            goal=goal.strip(),
            idempotency_key=idempotency_key,
            max_retries=max_retries,
            created_at=utcnow(),
        )

    # -- behaviors ----------------------------------------------------

    def start(self) -> None:
        if self._status is not TaskStatus.CREATED:
            raise InvalidStateTransition(f"cannot start a {self._status.value} task")
        self._status = TaskStatus.RUNNING
        self._attempts = 1
        self._started_at = utcnow()
        self._events.append(TaskStarted(task_id=self._id, attempt=self._attempts))

    def complete(self) -> None:
        if self._status is not TaskStatus.RUNNING:
            raise InvalidStateTransition(f"cannot complete a {self._status.value} task")
        self._status = TaskStatus.COMPLETED
        self._finished_at = utcnow()
        self._events.append(TaskCompleted(task_id=self._id))

    def fail(self, error: str) -> None:
        if self._status is not TaskStatus.RUNNING:
            raise InvalidStateTransition(f"cannot fail a {self._status.value} task")
        if not error.strip():
            raise DomainError("failure requires an error description")
        self._status = TaskStatus.FAILED
        self._error = error.strip()
        self._finished_at = utcnow()
        self._events.append(
            TaskFailed(task_id=self._id, error=self._error, attempts=self._attempts)
        )

    def retry(self) -> None:
        if self._status is not TaskStatus.FAILED:
            raise InvalidStateTransition(f"cannot retry a {self._status.value} task")
        retries_used = self._attempts - 1
        if retries_used >= self._max_retries:
            raise InvalidStateTransition(
                f"retry limit reached ({self._max_retries} retries after the first attempt)"
            )
        self._status = TaskStatus.RUNNING
        self._attempts += 1
        self._started_at = utcnow()
        self._finished_at = None
        self._error = None
        self._events.append(TaskStarted(task_id=self._id, attempt=self._attempts))

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
    def goal(self) -> str:
        return self._goal

    @property
    def idempotency_key(self) -> IdempotencyKey:
        return self._idempotency_key

    @property
    def status(self) -> TaskStatus:
        return self._status

    @property
    def attempts(self) -> int:
        return self._attempts

    @property
    def max_retries(self) -> int:
        return self._max_retries

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
    def created_at(self) -> datetime:
        return self._created_at
