"""Batch state for the D2 five-company prospect pipeline.

The aggregate stores orchestration progress and references existing Company,
Research, Opportunity, Contact and Outreach aggregates by id. It does not
duplicate any of those business models.
"""

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.exceptions import DomainError, InvalidStateTransition

PIPELINE_VERSION = "d2a-prospect-pipeline-v1"


class ProspectBatchStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"


class ProspectBatchCompanyStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class ProspectBatchStage(StrEnum):
    QUEUED = "queued"
    VALIDATING = "validating"
    RESEARCHING = "researching"
    AWAITING_EVIDENCE_REVIEW = "awaiting_evidence_review"
    SCORING = "scoring"
    DISCOVERING_CONTACT = "discovering_contact"
    GENERATING_DRAFT = "generating_draft"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


TERMINAL_COMPANY_STATUSES = frozenset(
    {
        ProspectBatchCompanyStatus.COMPLETED,
        ProspectBatchCompanyStatus.NEEDS_REVIEW,
        ProspectBatchCompanyStatus.FAILED,
    }
)


@dataclass(frozen=True)
class ProspectBatchCompany:
    company_id: UUID
    company_name: str
    position: int
    pipeline_version: str
    current_stage: ProspectBatchStage
    status: ProspectBatchCompanyStatus
    research_id: UUID | None
    opportunity_id: UUID | None
    selected_contact_id: UUID | None
    outreach_id: UUID | None
    draft_version: int | None
    score: float | None
    qualification_decision: str | None
    reasons: tuple[str, ...]
    contact_name: str | None
    contact_email: str | None
    contact_source_url: str | None
    draft_subject: str | None
    draft_status: str | None
    error_code: str | None
    error_summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    blocking_claim_count: int = 0
    resumed_at: datetime | None = None
    resumed_from_stage: ProspectBatchStage | None = None
    resume_count: int = 0

    def __post_init__(self) -> None:
        if self.position < 0:
            raise DomainError("batch company position must be nonnegative")
        if not self.company_name.strip():
            raise DomainError("batch company requires a name snapshot")
        if not self.pipeline_version.strip():
            raise DomainError("batch company requires a pipeline version")
        if self.blocking_claim_count < 0:
            raise DomainError("blocking_claim_count must be nonnegative")
        if self.resume_count < 0:
            raise DomainError("resume_count must be nonnegative")

    @classmethod
    def queued(
        cls, *, company_id: UUID, company_name: str, position: int
    ) -> "ProspectBatchCompany":
        return cls(
            company_id=company_id,
            company_name=company_name.strip(),
            position=position,
            pipeline_version=PIPELINE_VERSION,
            current_stage=ProspectBatchStage.QUEUED,
            status=ProspectBatchCompanyStatus.QUEUED,
            research_id=None,
            opportunity_id=None,
            selected_contact_id=None,
            outreach_id=None,
            draft_version=None,
            score=None,
            qualification_decision=None,
            reasons=(),
            contact_name=None,
            contact_email=None,
            contact_source_url=None,
            draft_subject=None,
            draft_status=None,
            error_code=None,
            error_summary=None,
            started_at=None,
            completed_at=None,
            blocking_claim_count=0,
            resumed_at=None,
            resumed_from_stage=None,
            resume_count=0,
        )

    def move_to(self, stage: ProspectBatchStage) -> "ProspectBatchCompany":
        if self.status in TERMINAL_COMPANY_STATUSES:
            raise InvalidStateTransition(
                f"cannot move a {self.status.value} company to {stage.value}"
            )
        return dataclasses.replace(
            self,
            current_stage=stage,
            status=ProspectBatchCompanyStatus.RUNNING,
            started_at=self.started_at or utcnow(),
            error_code=None,
            error_summary=None,
            completed_at=None,
        )

    def with_research(self, research_id: UUID) -> "ProspectBatchCompany":
        return dataclasses.replace(self, research_id=research_id)

    def with_opportunity(
        self,
        *,
        opportunity_id: UUID,
        score: float | None,
        qualification_decision: str | None,
        reasons: tuple[str, ...],
    ) -> "ProspectBatchCompany":
        return dataclasses.replace(
            self,
            opportunity_id=opportunity_id,
            score=score,
            qualification_decision=qualification_decision,
            reasons=reasons,
        )

    def with_contact(
        self,
        *,
        contact_id: UUID,
        name: str,
        email: str | None,
        source_url: str,
    ) -> "ProspectBatchCompany":
        return dataclasses.replace(
            self,
            selected_contact_id=contact_id,
            contact_name=name,
            contact_email=email,
            contact_source_url=source_url,
        )

    def with_draft(
        self,
        *,
        outreach_id: UUID,
        version: int,
        subject: str | None,
        status: str | None,
    ) -> "ProspectBatchCompany":
        return dataclasses.replace(
            self,
            outreach_id=outreach_id,
            draft_version=version,
            draft_subject=subject,
            draft_status=status,
        )

    def complete(self) -> "ProspectBatchCompany":
        if self.status is ProspectBatchCompanyStatus.COMPLETED:
            return self
        return dataclasses.replace(
            self,
            current_stage=ProspectBatchStage.COMPLETED,
            status=ProspectBatchCompanyStatus.COMPLETED,
            error_code=None,
            error_summary=None,
            completed_at=utcnow(),
        )

    def await_evidence_review(self, *, blocking_claim_count: int) -> "ProspectBatchCompany":
        if blocking_claim_count < 1:
            raise DomainError("evidence review requires at least one blocking claim")
        return dataclasses.replace(
            self,
            current_stage=ProspectBatchStage.AWAITING_EVIDENCE_REVIEW,
            status=ProspectBatchCompanyStatus.NEEDS_REVIEW,
            error_code="EVIDENCE_REVIEW_REQUIRED",
            error_summary="research claims were saved and require human confirmation",
            started_at=self.started_at or utcnow(),
            completed_at=utcnow(),
            blocking_claim_count=blocking_claim_count,
        )

    def needs_review(
        self,
        *,
        error_code: str,
        error_summary: str,
        stage: ProspectBatchStage = ProspectBatchStage.NEEDS_REVIEW,
    ) -> "ProspectBatchCompany":
        _require_error(error_code, error_summary)
        return dataclasses.replace(
            self,
            current_stage=stage,
            status=ProspectBatchCompanyStatus.NEEDS_REVIEW,
            error_code=error_code.strip(),
            error_summary=error_summary.strip(),
            started_at=self.started_at or utcnow(),
            completed_at=utcnow(),
        )

    def fail(self, *, error_code: str, error_summary: str) -> "ProspectBatchCompany":
        _require_error(error_code, error_summary)
        return dataclasses.replace(
            self,
            current_stage=ProspectBatchStage.FAILED,
            status=ProspectBatchCompanyStatus.FAILED,
            error_code=error_code.strip(),
            error_summary=error_summary.strip(),
            started_at=self.started_at or utcnow(),
            completed_at=utcnow(),
        )

    def retry(self) -> "ProspectBatchCompany":
        if self.status not in {
            ProspectBatchCompanyStatus.NEEDS_REVIEW,
            ProspectBatchCompanyStatus.FAILED,
        }:
            raise InvalidStateTransition(
                f"only failed or needs_review companies can be retried, got {self.status.value}"
            )
        return dataclasses.replace(
            self,
            current_stage=ProspectBatchStage.QUEUED,
            status=ProspectBatchCompanyStatus.QUEUED,
            error_code=None,
            error_summary=None,
            completed_at=None,
        )

    def resume_after_evidence_review(self) -> "ProspectBatchCompany":
        if (
            self.status is not ProspectBatchCompanyStatus.NEEDS_REVIEW
            or self.current_stage is not ProspectBatchStage.AWAITING_EVIDENCE_REVIEW
            or self.error_code != "EVIDENCE_REVIEW_REQUIRED"
        ):
            raise InvalidStateTransition(
                "only an awaiting_evidence_review company can be resumed"
            )
        now = utcnow()
        return dataclasses.replace(
            self,
            current_stage=ProspectBatchStage.SCORING,
            status=ProspectBatchCompanyStatus.RUNNING,
            error_code=None,
            error_summary=None,
            completed_at=None,
            resumed_at=now,
            resumed_from_stage=self.current_stage,
            resume_count=self.resume_count + 1,
        )


class ProspectBatch:
    def __init__(
        self,
        *,
        id: UUID,
        discovery_task_id: UUID,
        requested_count: int,
        effective_count: int,
        created_at: datetime,
        companies: list[ProspectBatchCompany],
    ) -> None:
        self._id = id
        self._discovery_task_id = discovery_task_id
        self._requested_count = requested_count
        self._effective_count = effective_count
        self._created_at = created_at
        self._companies = companies
        self._status = ProspectBatchStatus.PENDING
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None
        self._error_summary: str | None = None

    @classmethod
    def create(
        cls,
        *,
        discovery_task_id: UUID,
        requested_count: int,
        companies: tuple[tuple[UUID, str], ...],
    ) -> "ProspectBatch":
        if requested_count < 1:
            raise DomainError("batch requested_count must be positive")
        if not companies:
            raise DomainError("batch requires at least one company")
        if len(companies) > 5:
            raise DomainError("batch effective_count cannot exceed five")
        if len({company_id for company_id, _ in companies}) != len(companies):
            raise DomainError("batch companies must be deduplicated")
        return cls(
            id=uuid4(),
            discovery_task_id=discovery_task_id,
            requested_count=requested_count,
            effective_count=len(companies),
            created_at=utcnow(),
            companies=[
                ProspectBatchCompany.queued(
                    company_id=company_id, company_name=name, position=position
                )
                for position, (company_id, name) in enumerate(companies)
            ],
        )

    def start(self) -> None:
        if self._status not in {
            ProspectBatchStatus.PENDING,
            ProspectBatchStatus.RUNNING,
            ProspectBatchStatus.PARTIAL_FAILED,
            ProspectBatchStatus.FAILED,
        }:
            raise InvalidStateTransition(f"cannot start a {self._status.value} batch")
        self._status = ProspectBatchStatus.RUNNING
        self._started_at = self._started_at or utcnow()
        self._completed_at = None
        self._error_summary = None

    def replace_company(self, company: ProspectBatchCompany) -> None:
        for index, existing in enumerate(self._companies):
            if existing.company_id == company.company_id:
                self._companies[index] = company
                return
        raise DomainError(f"company is not part of this batch: {company.company_id}")

    def company(self, company_id: UUID) -> ProspectBatchCompany:
        for company in self._companies:
            if company.company_id == company_id:
                return company
        raise DomainError(f"company is not part of this batch: {company_id}")

    def finalize(self) -> None:
        if any(company.status not in TERMINAL_COMPANY_STATUSES for company in self._companies):
            raise InvalidStateTransition("cannot finalize while companies are still active")
        if self.completed_count == self._effective_count:
            self._status = ProspectBatchStatus.COMPLETED
        elif self.failed_count == self._effective_count:
            self._status = ProspectBatchStatus.FAILED
        else:
            self._status = ProspectBatchStatus.PARTIAL_FAILED
        errors = [
            f"{company.company_name}: {company.error_code}"
            for company in self._companies
            if company.error_code
        ]
        self._error_summary = "; ".join(errors) or None
        self._completed_at = utcnow()

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def discovery_task_id(self) -> UUID:
        return self._discovery_task_id

    @property
    def requested_count(self) -> int:
        return self._requested_count

    @property
    def effective_count(self) -> int:
        return self._effective_count

    @property
    def status(self) -> ProspectBatchStatus:
        return self._status

    @property
    def companies(self) -> tuple[ProspectBatchCompany, ...]:
        return tuple(sorted(self._companies, key=lambda item: item.position))

    @property
    def queued_count(self) -> int:
        return sum(c.status is ProspectBatchCompanyStatus.QUEUED for c in self._companies)

    @property
    def running_count(self) -> int:
        return sum(c.status is ProspectBatchCompanyStatus.RUNNING for c in self._companies)

    @property
    def completed_count(self) -> int:
        return sum(c.status is ProspectBatchCompanyStatus.COMPLETED for c in self._companies)

    @property
    def needs_review_count(self) -> int:
        return sum(c.status is ProspectBatchCompanyStatus.NEEDS_REVIEW for c in self._companies)

    @property
    def failed_count(self) -> int:
        return sum(c.status is ProspectBatchCompanyStatus.FAILED for c in self._companies)

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def started_at(self) -> datetime | None:
        return self._started_at

    @property
    def completed_at(self) -> datetime | None:
        return self._completed_at

    @property
    def error_summary(self) -> str | None:
        return self._error_summary


def _require_error(error_code: str, error_summary: str) -> None:
    if not error_code.strip() or not error_summary.strip():
        raise DomainError("terminal batch company state requires an error code and summary")
