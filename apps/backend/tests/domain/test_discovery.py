"""Discovery context: value objects, DiscoveryRun state machine, events,
and the boundary rule that Discovery never touches other aggregates."""

import ast
import dataclasses
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

import app.domain.discovery
from app.domain.discovery import (
    DiscoveryResult,
    DiscoveryRun,
    DiscoveryRunStatus,
    DiscoveryStats,
    RawCompanySnapshot,
    Signal,
)
from app.domain.events import CompanyDiscovered, DiscoveryCompleted, DiscoveryFailed
from app.domain.exceptions import DomainError, InvalidStateTransition
from app.domain.values import Evidence, SourceReference


@pytest.fixture
def snapshot() -> RawCompanySnapshot:
    return RawCompanySnapshot(
        name_text="Pacific Home Goods Inc",
        source=SourceReference(
            source="importyeti",
            reference="https://example.com/company/phg",
            retrieved_at=datetime(2026, 7, 1, tzinfo=UTC),
        ),
        website_text="pacifichomegoods.com",
        location_text="Los Angeles, CA",
    )


@pytest.fixture
def result(snapshot: RawCompanySnapshot) -> DiscoveryResult:
    return DiscoveryResult(
        snapshot=snapshot,
        evidence=(
            Evidence(claim="~40 FCL from CNSHA in Q2", sources=(snapshot.source,)),
        ),
        signals=(Signal(kind="volume_trend", detail="growing 3 quarters straight"),),
    )


@pytest.fixture
def run() -> DiscoveryRun:
    return DiscoveryRun.create("furniture importers on CNSHA-USLAX", user_id=uuid4())


class TestValueObjects:
    def test_snapshot_requires_name_text(self, snapshot: RawCompanySnapshot) -> None:
        with pytest.raises(DomainError):
            RawCompanySnapshot(name_text="  ", source=snapshot.source)

    def test_snapshot_is_immutable(self, snapshot: RawCompanySnapshot) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            snapshot.name_text = "tampered"  # type: ignore[misc]

    @pytest.mark.parametrize(("kind", "detail"), [("", "x"), ("volume", "  ")])
    def test_signal_validation(self, kind: str, detail: str) -> None:
        with pytest.raises(DomainError):
            Signal(kind=kind, detail=detail)

    def test_signal_equality_is_value_based(self) -> None:
        assert Signal(kind="a", detail="b") == Signal(kind="a", detail="b")

    def test_result_is_immutable(self, result: DiscoveryResult) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.signals = ()  # type: ignore[misc]

    @pytest.mark.parametrize(
        "stats",
        [
            {"discovered": -1, "succeeded": 0, "failed": 0},
            {"discovered": 0, "succeeded": -1, "failed": 0},
            {"discovered": 0, "succeeded": 0, "failed": -1},
        ],
    )
    def test_stats_must_be_non_negative(self, stats: dict[str, int]) -> None:
        with pytest.raises(DomainError):
            DiscoveryStats(**stats)


class TestLifecycle:
    def test_create(self, run: DiscoveryRun) -> None:
        assert run.status is DiscoveryRunStatus.CREATED
        assert run.started_at is None
        assert run.stats == DiscoveryStats()
        assert run.drain_events() == ()

    def test_criteria_required(self) -> None:
        with pytest.raises(DomainError):
            DiscoveryRun.create("   ", user_id=uuid4())

    def test_full_successful_run(self, run: DiscoveryRun, result: DiscoveryResult) -> None:
        run.start()
        assert run.started_at is not None
        run.record_success([result, result])
        run.record_failure("linkedin query timed out")
        run.complete()
        assert run.status is DiscoveryRunStatus.COMPLETED
        assert run.finished_at is not None
        assert run.stats == DiscoveryStats(discovered=2, succeeded=1, failed=1)
        assert run.results == (result, result)

    def test_failed_run(self, run: DiscoveryRun) -> None:
        run.start()
        run.fail("all sources unreachable")
        assert run.status is DiscoveryRunStatus.FAILED
        assert run.error == "all sources unreachable"
        assert run.finished_at is not None


class TestIllegalTransitions:
    def test_cannot_start_twice(self, run: DiscoveryRun) -> None:
        run.start()
        with pytest.raises(InvalidStateTransition):
            run.start()

    def test_cannot_record_before_start(self, run: DiscoveryRun, result: DiscoveryResult) -> None:
        with pytest.raises(InvalidStateTransition):
            run.record_success([result])
        with pytest.raises(InvalidStateTransition):
            run.record_failure("too early")

    def test_cannot_complete_before_start(self, run: DiscoveryRun) -> None:
        with pytest.raises(InvalidStateTransition):
            run.complete()

    def test_terminal_blocks_everything(self, run: DiscoveryRun, result: DiscoveryResult) -> None:
        run.start()
        run.complete()
        with pytest.raises(InvalidStateTransition):
            run.record_success([result])
        with pytest.raises(InvalidStateTransition):
            run.fail("late failure")
        with pytest.raises(InvalidStateTransition):
            run.start()

    def test_failure_requires_reason(self, run: DiscoveryRun) -> None:
        run.start()
        with pytest.raises(DomainError):
            run.record_failure("  ")
        with pytest.raises(DomainError):
            run.fail("  ")


class TestEvents:
    def test_company_discovered_per_result(
        self, run: DiscoveryRun, result: DiscoveryResult
    ) -> None:
        run.start()
        run.record_success([result, result])
        events = run.drain_events()
        assert len(events) == 2
        assert all(isinstance(e, CompanyDiscovered) for e in events)
        first = events[0]
        assert isinstance(first, CompanyDiscovered)
        assert first.run_id == run.id
        assert first.result == result

    def test_completed_event_carries_stats(
        self, run: DiscoveryRun, result: DiscoveryResult
    ) -> None:
        run.start()
        run.record_success([result])
        run.drain_events()
        run.complete()
        events = run.drain_events()
        assert len(events) == 1
        completed = events[0]
        assert isinstance(completed, DiscoveryCompleted)
        assert completed.stats == DiscoveryStats(discovered=1, succeeded=1, failed=0)

    def test_failed_event_carries_error_and_stats(self, run: DiscoveryRun) -> None:
        run.start()
        run.record_failure("importyeti 429")
        run.fail("rate limited everywhere")
        events = run.drain_events()
        failed = events[-1]
        assert isinstance(failed, DiscoveryFailed)
        assert failed.error == "rate limited everywhere"
        assert failed.stats == DiscoveryStats(failed=1)

    def test_drain_is_safe_to_repeat(self, run: DiscoveryRun, result: DiscoveryResult) -> None:
        run.start()
        run.record_success([result])
        assert len(run.drain_events()) == 1
        assert run.drain_events() == ()


class TestContextBoundary:
    def test_discovery_never_imports_other_aggregates(self) -> None:
        """Discovery produces events only — it must not know Company,
        Opportunity or Outreach (ADR-0018)."""
        discovery_root = Path(app.domain.discovery.__file__).parent
        forbidden = (
            "app.domain.company",
            "app.domain.opportunity",
            "app.domain.outreach",
            "app.domain.task",
        )
        violations: list[str] = []
        for path in sorted(discovery_root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                violations.extend(
                    f"{path.name} imports {module}"
                    for module in modules
                    if module.startswith(forbidden)
                )
        assert not violations, "\n".join(violations)

    def test_run_has_no_company_or_scoring_surface(self, run: DiscoveryRun) -> None:
        for forbidden in ("create_company", "score", "rescore", "qualify"):
            assert not hasattr(run, forbidden)
