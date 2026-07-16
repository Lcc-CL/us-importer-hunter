"""Task aggregate: execution lifecycle, retry limits, idempotency."""

import pytest

from app.domain.events import TaskCompleted, TaskFailed, TaskStarted
from app.domain.exceptions import (
    DomainError,
    DuplicateOperation,
    InvalidStateTransition,
)
from app.domain.task import Task, TaskStatus
from app.domain.values import IdempotencyKey


def make_task(max_retries: int = 3) -> Task:
    return Task.create(
        "hunt furniture importers on CNSHA-USLAX",
        IdempotencyKey.from_parts("hunt", "user-1"),
        max_retries=max_retries,
    )


class TestLifecycle:
    def test_start_sets_started_at(self) -> None:
        task = make_task()
        task.start()
        assert task.status is TaskStatus.RUNNING
        assert task.started_at is not None
        assert task.attempts == 1
        events = task.drain_events()
        assert isinstance(events[0], TaskStarted)

    def test_complete_sets_finished_at(self) -> None:
        task = make_task()
        task.start()
        task.complete()
        assert task.status is TaskStatus.COMPLETED
        assert task.finished_at is not None
        assert any(isinstance(e, TaskCompleted) for e in task.drain_events())

    def test_fail_records_diagnosis(self) -> None:
        task = make_task()
        task.start()
        task.fail("importyeti tool timeout")
        assert task.status is TaskStatus.FAILED
        assert task.error == "importyeti tool timeout"
        failed = [e for e in task.drain_events() if isinstance(e, TaskFailed)]
        assert failed[0].error == "importyeti tool timeout"

    def test_fail_requires_error(self) -> None:
        task = make_task()
        task.start()
        with pytest.raises(DomainError):
            task.fail("  ")

    def test_goal_required(self) -> None:
        with pytest.raises(DomainError):
            Task.create("  ", IdempotencyKey("k"))


class TestIllegalTransitions:
    def test_completed_cannot_restart(self) -> None:
        task = make_task()
        task.start()
        task.complete()
        with pytest.raises(InvalidStateTransition):
            task.start()
        with pytest.raises(InvalidStateTransition):
            task.retry()

    def test_cannot_start_twice(self) -> None:
        task = make_task()
        task.start()
        with pytest.raises(InvalidStateTransition):
            task.start()

    def test_cannot_complete_unstarted(self) -> None:
        task = make_task()
        with pytest.raises(InvalidStateTransition):
            task.complete()

    def test_cannot_retry_running(self) -> None:
        task = make_task()
        task.start()
        with pytest.raises(InvalidStateTransition):
            task.retry()


class TestRetry:
    def test_retry_resets_error_and_increments_attempts(self) -> None:
        task = make_task()
        task.start()
        task.fail("timeout")
        task.retry()
        assert task.status is TaskStatus.RUNNING
        assert task.attempts == 2
        assert task.error is None
        assert task.finished_at is None

    def test_retry_limit_enforced(self) -> None:
        task = make_task(max_retries=1)
        task.start()
        task.fail("boom 1")
        task.retry()
        task.fail("boom 2")
        with pytest.raises(InvalidStateTransition, match="retry limit"):
            task.retry()

    def test_retry_emits_started_with_attempt(self) -> None:
        task = make_task()
        task.start()
        task.fail("boom")
        task.drain_events()
        task.retry()
        events = task.drain_events()
        assert isinstance(events[0], TaskStarted)
        assert events[0].attempt == 2


class TestIdempotency:
    def test_duplicate_active_key_rejected(self) -> None:
        key = IdempotencyKey.from_parts("hunt", "user-1")
        with pytest.raises(DuplicateOperation):
            Task.create("another hunt", key, active_keys={key})

    def test_distinct_keys_allowed(self) -> None:
        key = IdempotencyKey.from_parts("hunt", "user-1")
        other = IdempotencyKey.from_parts("hunt", "user-2")
        task = Task.create("hunt", key, active_keys={other})
        assert task.idempotency_key == key

    def test_key_equality_is_value_based(self) -> None:
        assert IdempotencyKey("a:b") == IdempotencyKey.from_parts("a", "b")


class TestAttemptHistory:
    """One append-only record per finished attempt (L4 review follow-up)."""

    def test_completed_attempt_recorded(self) -> None:
        task = make_task()
        task.start()
        task.complete()
        assert len(task.attempt_history) == 1
        attempt = task.attempt_history[0]
        assert attempt.number == 1
        assert attempt.succeeded is True
        assert attempt.finished_at >= attempt.started_at

    def test_failure_and_retry_accumulate_records(self) -> None:
        task = make_task()
        task.start()
        task.fail("timeout")
        task.retry()
        task.complete()
        history = task.attempt_history
        assert [a.number for a in history] == [1, 2]
        assert history[0].succeeded is False
        assert history[0].error == "timeout"
        assert history[1].succeeded is True

    def test_running_attempt_not_yet_in_history(self) -> None:
        task = make_task()
        task.start()
        assert task.attempt_history == ()

    def test_attempt_record_is_immutable(self) -> None:
        import dataclasses

        task = make_task()
        task.start()
        task.complete()
        with pytest.raises(dataclasses.FrozenInstanceError):
            task.attempt_history[0].error = "tampered"  # type: ignore[misc]


class TestEventDrain:
    def test_drain_is_safe_to_repeat(self) -> None:
        task = make_task()
        task.start()
        assert len(task.drain_events()) == 1
        assert task.drain_events() == ()
