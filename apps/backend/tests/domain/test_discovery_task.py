"""Discovery task lifecycle and independent candidate failure accounting."""

from uuid import uuid4

import pytest

from app.domain.clock import utcnow
from app.domain.discovery import (
    DiscoveryCandidate,
    DiscoveryCandidateStatus,
    DiscoveryTask,
    DiscoveryTaskStatus,
)
from app.domain.exceptions import DomainError, InvalidStateTransition


def make_task() -> DiscoveryTask:
    return DiscoveryTask.create(
        execution_task_id=uuid4(),
        original_prompt="帮我找 20 家北美五金进口商",
        requested_count=20,
        effective_count=20,
        parsed_region="North America",
        parsed_category="hardware",
        parsed_keywords=("五金", "hardware", "importer"),
        provider="manual_csv",
    )


def make_candidate(name: str) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        id=uuid4(),
        position=0,
        source="manual_csv",
        source_url=f"https://evidence.example/{name.lower()}",
        external_id=None,
        company_name=name,
        normalized_name=name.lower(),
        website=f"https://{name.lower()}.example",
        normalized_domain=f"{name.lower()}.example",
        address=None,
        region="US",
        product_description="Hardware",
        import_evidence="Bill of lading reference",
        raw_metadata_json="{}",
        status=DiscoveryCandidateStatus.DISCOVERED,
        company_id=None,
        duplicate_of_id=None,
        failure_reason=None,
        created_at=utcnow(),
    )


def test_completed_counts_ingested_and_duplicates() -> None:
    task = make_task()
    task.start()
    first = make_candidate("Atlas").ingested(uuid4())
    duplicate = make_candidate("AtlasAlias").duplicate(duplicate_of_id=first.id)
    task.add_candidate(first)
    task.add_candidate(duplicate)
    task.complete()
    assert task.status is DiscoveryTaskStatus.COMPLETED
    assert task.discovered_count == 2
    assert task.ingested_count == 1
    assert task.duplicate_count == 1
    assert task.failed_count == 0


def test_candidate_failure_allows_partial_completion() -> None:
    task = make_task()
    task.start()
    task.add_candidate(make_candidate("Atlas").ingested(uuid4()))
    task.add_candidate(make_candidate("Broken").failed("provider row rejected"))
    task.complete(
        provider_failures=1,
        error_code="DISCOVERY_RESULT_ERRORS",
        error_summary="one provider row failed",
    )
    assert task.status is DiscoveryTaskStatus.PARTIAL_FAILED
    assert task.failed_count == 2
    assert task.provider_failure_count == 1


def test_all_failed_candidates_make_task_failed() -> None:
    task = make_task()
    task.start()
    task.add_candidate(make_candidate("Broken").failed("ingestion failed"))
    task.complete(
        error_code="DISCOVERY_RESULT_ERRORS",
        error_summary="all candidates failed",
    )
    assert task.status is DiscoveryTaskStatus.FAILED


def test_failed_completion_requires_structured_error_without_mutating_status() -> None:
    task = make_task()
    task.start()
    task.add_candidate(make_candidate("Broken").failed("ingestion failed"))
    with pytest.raises(DomainError, match="error code and summary"):
        task.complete()
    assert task.status is DiscoveryTaskStatus.RUNNING


def test_terminal_task_cannot_restart_and_failure_has_machine_code() -> None:
    task = make_task()
    task.start()
    task.fail(error_code="DISCOVERY_PROVIDER_ERROR", error_summary="provider failed")
    assert task.completed_at is not None
    assert task.error_code == "DISCOVERY_PROVIDER_ERROR"
    assert task.failed_count == 1
    with pytest.raises(InvalidStateTransition):
        task.start()
