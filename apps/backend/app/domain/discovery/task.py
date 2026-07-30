"""Discovery-task aggregate: parsed target plus persisted company claims."""

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.domain.clock import utcnow
from app.domain.exceptions import DomainError, InvalidStateTransition


class DiscoveryTaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"


class DiscoveryCandidateStatus(StrEnum):
    DISCOVERED = "discovered"
    INGESTED = "ingested"
    DUPLICATE = "duplicate"
    FAILED = "failed"


@dataclass(frozen=True)
class DiscoveryCandidate:
    id: UUID
    source: str
    source_url: str | None
    external_id: str | None
    company_name: str
    normalized_name: str
    website: str | None
    normalized_domain: str | None
    address: str | None
    region: str | None
    product_description: str | None
    import_evidence: str | None
    raw_metadata_json: str
    status: DiscoveryCandidateStatus
    company_id: UUID | None
    duplicate_of_id: UUID | None
    failure_reason: str | None
    created_at: datetime

    def ingested(self, company_id: UUID) -> "DiscoveryCandidate":
        return dataclasses.replace(
            self,
            status=DiscoveryCandidateStatus.INGESTED,
            company_id=company_id,
            failure_reason=None,
        )

    def duplicate(
        self, *, duplicate_of_id: UUID | None, company_id: UUID | None = None
    ) -> "DiscoveryCandidate":
        return dataclasses.replace(
            self,
            status=DiscoveryCandidateStatus.DUPLICATE,
            duplicate_of_id=duplicate_of_id,
            company_id=company_id,
            failure_reason=None,
        )

    def failed(self, reason: str) -> "DiscoveryCandidate":
        if not reason.strip():
            raise DomainError("candidate failure requires a reason")
        return dataclasses.replace(
            self,
            status=DiscoveryCandidateStatus.FAILED,
            failure_reason=reason.strip(),
        )


class DiscoveryTask:
    """Discovery-specific state linked 1:1 to the generic execution Task."""

    def __init__(
        self,
        *,
        id: UUID,
        original_prompt: str,
        requested_count: int,
        effective_count: int,
        parsed_region: str,
        parsed_category: str,
        parsed_keywords: tuple[str, ...],
        provider: str,
        created_at: datetime,
    ) -> None:
        self._id = id
        self._original_prompt = original_prompt
        self._requested_count = requested_count
        self._effective_count = effective_count
        self._parsed_region = parsed_region
        self._parsed_category = parsed_category
        self._parsed_keywords = parsed_keywords
        self._provider = provider
        self._created_at = created_at
        self._status = DiscoveryTaskStatus.PENDING
        self._error_summary: str | None = None
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None
        self._provider_failure_count = 0
        self._candidates: list[DiscoveryCandidate] = []

    @classmethod
    def create(
        cls,
        *,
        execution_task_id: UUID,
        original_prompt: str,
        requested_count: int,
        effective_count: int,
        parsed_region: str,
        parsed_category: str,
        parsed_keywords: tuple[str, ...],
        provider: str,
    ) -> "DiscoveryTask":
        if requested_count < 1 or effective_count < 1:
            raise DomainError("discovery counts must be positive")
        if effective_count > requested_count:
            raise DomainError("effective count cannot exceed requested count")
        if not original_prompt.strip():
            raise DomainError("discovery task requires an original prompt")
        if not parsed_region.strip():
            raise DomainError("discovery task requires a parsed region")
        if not parsed_category.strip():
            raise DomainError("discovery task requires a parsed category")
        if not provider.strip():
            raise DomainError("discovery task requires a provider")
        return cls(
            id=execution_task_id,
            original_prompt=original_prompt.strip(),
            requested_count=requested_count,
            effective_count=effective_count,
            parsed_region=parsed_region.strip(),
            parsed_category=parsed_category.strip(),
            parsed_keywords=parsed_keywords,
            provider=provider.strip(),
            created_at=utcnow(),
        )

    def start(self) -> None:
        if self._status is not DiscoveryTaskStatus.PENDING:
            raise InvalidStateTransition(f"cannot start a {self._status.value} discovery task")
        self._status = DiscoveryTaskStatus.RUNNING
        self._started_at = utcnow()

    def add_candidate(self, candidate: DiscoveryCandidate) -> None:
        if self._status is not DiscoveryTaskStatus.RUNNING:
            raise InvalidStateTransition("candidates can only be added while discovery is running")
        if len(self._candidates) >= self._effective_count:
            return
        if any(existing.id == candidate.id for existing in self._candidates):
            raise DomainError(f"candidate already exists: {candidate.id}")
        self._candidates.append(candidate)

    def replace_candidate(self, candidate: DiscoveryCandidate) -> None:
        for index, existing in enumerate(self._candidates):
            if existing.id == candidate.id:
                self._candidates[index] = candidate
                return
        raise DomainError(f"candidate was not found: {candidate.id}")

    def complete(self, *, provider_failures: int = 0, error_summary: str | None = None) -> None:
        if self._status is not DiscoveryTaskStatus.RUNNING:
            raise InvalidStateTransition(f"cannot complete a {self._status.value} discovery task")
        self._provider_failure_count = max(0, provider_failures)
        failed = self.failed_count
        processed = self.ingested_count + self.duplicate_count
        if failed and processed:
            self._status = DiscoveryTaskStatus.PARTIAL_FAILED
        elif failed and not processed:
            self._status = DiscoveryTaskStatus.FAILED
        else:
            self._status = DiscoveryTaskStatus.COMPLETED
        self._error_summary = (
            error_summary.strip() if error_summary and error_summary.strip() else None
        )
        self._completed_at = utcnow()

    def fail(self, error: str) -> None:
        if self._status is not DiscoveryTaskStatus.RUNNING:
            raise InvalidStateTransition(f"cannot fail a {self._status.value} discovery task")
        if not error.strip():
            raise DomainError("discovery task failure requires an error")
        self._status = DiscoveryTaskStatus.FAILED
        self._error_summary = error.strip()
        self._completed_at = utcnow()

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def original_prompt(self) -> str:
        return self._original_prompt

    @property
    def requested_count(self) -> int:
        return self._requested_count

    @property
    def effective_count(self) -> int:
        return self._effective_count

    @property
    def parsed_region(self) -> str:
        return self._parsed_region

    @property
    def parsed_category(self) -> str:
        return self._parsed_category

    @property
    def parsed_keywords(self) -> tuple[str, ...]:
        return self._parsed_keywords

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def status(self) -> DiscoveryTaskStatus:
        return self._status

    @property
    def discovered_count(self) -> int:
        return len(self._candidates)

    @property
    def ingested_count(self) -> int:
        return sum(c.status is DiscoveryCandidateStatus.INGESTED for c in self._candidates)

    @property
    def duplicate_count(self) -> int:
        return sum(c.status is DiscoveryCandidateStatus.DUPLICATE for c in self._candidates)

    @property
    def failed_count(self) -> int:
        candidate_failures = sum(
            c.status is DiscoveryCandidateStatus.FAILED for c in self._candidates
        )
        return candidate_failures + self._provider_failure_count

    @property
    def provider_failure_count(self) -> int:
        return self._provider_failure_count

    @property
    def error_summary(self) -> str | None:
        return self._error_summary

    @property
    def candidates(self) -> tuple[DiscoveryCandidate, ...]:
        return tuple(self._candidates)

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def started_at(self) -> datetime | None:
        return self._started_at

    @property
    def completed_at(self) -> datetime | None:
        return self._completed_at
