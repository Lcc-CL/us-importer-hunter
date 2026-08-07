"""Framework-free state for auditable import entity resolution."""

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.exceptions import DomainError, InvalidStateTransition


class ImportResolutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"


class ImportEntityType(StrEnum):
    COMPANY = "company"
    CONTACT = "contact"


class ImportEntityDecisionKind(StrEnum):
    AUTO_CREATE = "auto_create"
    AUTO_MERGE = "auto_merge"
    REVIEW_REQUIRED = "review_required"
    MANUAL_MERGE = "manual_merge"
    KEEP_SEPARATE = "keep_separate"
    REJECTED = "rejected"


class ImportEntityReviewStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    REVIEWED = "reviewed"


class ImportReviewAction(StrEnum):
    MERGE = "merge"
    KEEP_SEPARATE = "keep_separate"
    REJECT = "reject"


class CompanyContactStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


class ImportRoleCategory(StrEnum):
    OWNER_FOUNDER = "owner_founder"
    EXECUTIVE = "executive"
    PROCUREMENT = "procurement"
    SUPPLY_CHAIN = "supply_chain"
    LOGISTICS = "logistics"
    OPERATIONS = "operations"
    IMPORT_EXPORT = "import_export"
    WAREHOUSE = "warehouse"
    SALES = "sales"
    GENERAL_DEPARTMENT = "general_department"
    IRRELEVANT = "irrelevant"
    UNKNOWN = "unknown"


class ImportJobStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImportJobType(StrEnum):
    ENTITY_RESOLUTION = "entity_resolution"
    PROSPECT_ROUTING = "prospect_routing"


ACTIVE_IMPORT_JOB_STATUSES = frozenset(
    {ImportJobStatus.PENDING, ImportJobStatus.LEASED, ImportJobStatus.RUNNING}
)


@dataclass(frozen=True)
class CompanyExternalIdentity:
    id: UUID
    company_id: UUID
    source: str
    external_id: str
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls, *, company_id: UUID, source: str, external_id: str, seen_at: datetime
    ) -> "CompanyExternalIdentity":
        normalized_source = source.strip().lower()
        normalized_external_id = external_id.strip()
        if not normalized_source or not normalized_external_id:
            raise DomainError("company external identity requires source and external id")
        return cls(
            id=uuid4(),
            company_id=company_id,
            source=normalized_source,
            external_id=normalized_external_id,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            created_at=seen_at,
            updated_at=seen_at,
        )

    def seen_again(self, seen_at: datetime) -> "CompanyExternalIdentity":
        return dataclasses.replace(
            self,
            first_seen_at=min(self.first_seen_at, seen_at),
            last_seen_at=max(self.last_seen_at, seen_at),
            updated_at=max(self.updated_at, seen_at),
        )


@dataclass(frozen=True)
class CompanyResolutionProfile:
    company_id: UUID
    normalized_name: str
    normalized_domain: str | None
    normalized_address: str | None
    company_type: str | None
    normalized_phone: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    source_import_row_id: UUID | None
    created_at: datetime
    updated_at: datetime

    def seen_again(
        self,
        *,
        normalized_name: str,
        normalized_domain: str | None,
        normalized_address: str | None,
        company_type: str | None,
        normalized_phone: str | None,
        seen_at: datetime,
    ) -> "CompanyResolutionProfile":
        return dataclasses.replace(
            self,
            normalized_name=self.normalized_name or normalized_name,
            normalized_domain=self.normalized_domain or normalized_domain,
            normalized_address=self.normalized_address or normalized_address,
            company_type=self.company_type or company_type,
            normalized_phone=self.normalized_phone or normalized_phone,
            first_seen_at=min(self.first_seen_at, seen_at),
            last_seen_at=max(self.last_seen_at, seen_at),
            updated_at=max(self.updated_at, seen_at),
        )


@dataclass(frozen=True)
class CompanyContact:
    id: UUID
    company_id: UUID
    contact_id: UUID
    raw_title: str | None
    role_category: ImportRoleCategory
    seniority: str
    is_department_contact: bool
    status: CompanyContactStatus
    first_seen_at: datetime
    last_seen_at: datetime
    source_import_row_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        company_id: UUID,
        contact_id: UUID,
        raw_title: str | None,
        role_category: ImportRoleCategory,
        seniority: str,
        is_department_contact: bool,
        source_import_row_id: UUID | None,
        seen_at: datetime,
    ) -> "CompanyContact":
        return cls(
            id=uuid4(),
            company_id=company_id,
            contact_id=contact_id,
            raw_title=raw_title,
            role_category=role_category,
            seniority=seniority,
            is_department_contact=is_department_contact,
            status=CompanyContactStatus.ACTIVE,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            source_import_row_id=source_import_row_id,
            created_at=seen_at,
            updated_at=seen_at,
        )

    def seen_again(
        self,
        *,
        raw_title: str | None,
        role_category: ImportRoleCategory,
        seniority: str,
        is_department_contact: bool,
        seen_at: datetime,
    ) -> "CompanyContact":
        return dataclasses.replace(
            self,
            raw_title=self.raw_title or raw_title,
            role_category=(
                self.role_category
                if self.role_category is not ImportRoleCategory.UNKNOWN
                else role_category
            ),
            seniority=self.seniority if self.seniority != "unknown" else seniority,
            is_department_contact=self.is_department_contact or is_department_contact,
            status=CompanyContactStatus.ACTIVE,
            first_seen_at=min(self.first_seen_at, seen_at),
            last_seen_at=max(self.last_seen_at, seen_at),
            updated_at=max(self.updated_at, seen_at),
        )


@dataclass(frozen=True)
class ImportEntityDecision:
    id: UUID
    import_session_id: UUID
    raw_import_row_id: UUID
    entity_type: ImportEntityType
    candidate_entity_id: UUID | None
    decision: ImportEntityDecisionKind
    confidence: float
    reason_codes: tuple[str, ...]
    review_status: ImportEntityReviewStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise DomainError("import entity decision confidence must be within 0-1")
        if not self.reason_codes:
            raise DomainError("import entity decision requires reason codes")
        if self.decision is ImportEntityDecisionKind.REVIEW_REQUIRED:
            if self.review_status is not ImportEntityReviewStatus.PENDING:
                raise DomainError("review-required decisions must be pending")
            if self.candidate_entity_id is None:
                raise DomainError("review-required decisions need a candidate")

    @classmethod
    def create(
        cls,
        *,
        import_session_id: UUID,
        raw_import_row_id: UUID,
        entity_type: ImportEntityType,
        candidate_entity_id: UUID | None,
        decision: ImportEntityDecisionKind,
        confidence: float,
        reason_codes: tuple[str, ...],
        now: datetime | None = None,
    ) -> "ImportEntityDecision":
        created_at = now or utcnow()
        review_status = (
            ImportEntityReviewStatus.PENDING
            if decision is ImportEntityDecisionKind.REVIEW_REQUIRED
            else ImportEntityReviewStatus.NOT_REQUIRED
        )
        return cls(
            id=uuid4(),
            import_session_id=import_session_id,
            raw_import_row_id=raw_import_row_id,
            entity_type=entity_type,
            candidate_entity_id=candidate_entity_id,
            decision=decision,
            confidence=confidence,
            reason_codes=reason_codes,
            review_status=review_status,
            reviewed_by=None,
            reviewed_at=None,
            created_at=created_at,
            updated_at=created_at,
        )

    def review(
        self,
        *,
        action: ImportReviewAction,
        candidate_entity_id: UUID | None,
        reviewed_by: str,
        now: datetime | None = None,
    ) -> "ImportEntityDecision":
        reviewer = reviewed_by.strip()
        if not reviewer:
            raise DomainError("entity review requires a reviewer")
        target_decision = {
            ImportReviewAction.MERGE: ImportEntityDecisionKind.MANUAL_MERGE,
            ImportReviewAction.KEEP_SEPARATE: ImportEntityDecisionKind.KEEP_SEPARATE,
            ImportReviewAction.REJECT: ImportEntityDecisionKind.REJECTED,
        }[action]
        if self.review_status is ImportEntityReviewStatus.REVIEWED:
            if self.decision is target_decision:
                return self
            raise InvalidStateTransition("entity decision was already reviewed differently")
        if self.review_status is not ImportEntityReviewStatus.PENDING:
            raise InvalidStateTransition("entity decision does not require review")
        if target_decision is ImportEntityDecisionKind.MANUAL_MERGE and candidate_entity_id is None:
            raise DomainError("manual merge requires a candidate entity")
        reviewed_at = now or utcnow()
        return dataclasses.replace(
            self,
            candidate_entity_id=candidate_entity_id,
            decision=target_decision,
            review_status=ImportEntityReviewStatus.REVIEWED,
            reviewed_by=reviewer,
            reviewed_at=reviewed_at,
            updated_at=reviewed_at,
        )


class ImportResolution:
    def __init__(
        self,
        *,
        import_session_id: UUID,
        status: ImportResolutionStatus,
        total_rows: int,
        processed_rows: int,
        companies_created: int,
        companies_reused: int,
        company_reviews_required: int,
        contacts_created: int,
        contacts_reused: int,
        company_contacts_created: int,
        invalid_rows: int,
        failed_rows: int,
        started_at: datetime | None,
        completed_at: datetime | None,
        error_summary: str | None,
        created_at: datetime,
        updated_at: datetime,
    ) -> None:
        self.import_session_id = import_session_id
        self.status = status
        self.total_rows = total_rows
        self.processed_rows = processed_rows
        self.companies_created = companies_created
        self.companies_reused = companies_reused
        self.company_reviews_required = company_reviews_required
        self.contacts_created = contacts_created
        self.contacts_reused = contacts_reused
        self.company_contacts_created = company_contacts_created
        self.invalid_rows = invalid_rows
        self.failed_rows = failed_rows
        self.started_at = started_at
        self.completed_at = completed_at
        self.error_summary = error_summary
        self.created_at = created_at
        self.updated_at = updated_at
        self._validate()

    @classmethod
    def create(
        cls, *, import_session_id: UUID, total_rows: int, invalid_rows: int
    ) -> "ImportResolution":
        now = utcnow()
        return cls(
            import_session_id=import_session_id,
            status=ImportResolutionStatus.PENDING,
            total_rows=total_rows,
            processed_rows=0,
            companies_created=0,
            companies_reused=0,
            company_reviews_required=0,
            contacts_created=0,
            contacts_reused=0,
            company_contacts_created=0,
            invalid_rows=invalid_rows,
            failed_rows=0,
            started_at=None,
            completed_at=None,
            error_summary=None,
            created_at=now,
            updated_at=now,
        )

    def start(self) -> None:
        if self.status in {ImportResolutionStatus.COMPLETED, ImportResolutionStatus.PARTIAL_FAILED}:
            return
        if self.status is ImportResolutionStatus.FAILED:
            raise InvalidStateTransition("failed import resolution requires resubmission")
        now = utcnow()
        self.status = ImportResolutionStatus.RUNNING
        self.started_at = self.started_at or now
        self.updated_at = now
        self.error_summary = None

    def record_row(
        self,
        *,
        company_decision: ImportEntityDecisionKind | None,
        contact_decision: ImportEntityDecisionKind | None,
        company_contact_created: bool,
        failed: bool,
    ) -> None:
        if self.status is not ImportResolutionStatus.RUNNING:
            raise InvalidStateTransition("rows can only be recorded while resolution is running")
        self.processed_rows += 1
        if company_decision is ImportEntityDecisionKind.AUTO_CREATE:
            self.companies_created += 1
        elif company_decision is ImportEntityDecisionKind.AUTO_MERGE:
            self.companies_reused += 1
        elif company_decision is ImportEntityDecisionKind.REVIEW_REQUIRED:
            self.company_reviews_required += 1
        if contact_decision is ImportEntityDecisionKind.AUTO_CREATE:
            self.contacts_created += 1
        elif contact_decision is ImportEntityDecisionKind.AUTO_MERGE:
            self.contacts_reused += 1
        if company_contact_created:
            self.company_contacts_created += 1
        if failed:
            self.failed_rows += 1
        self.updated_at = utcnow()
        self._validate()

    def record_review(
        self,
        *,
        entity_type: ImportEntityType,
        action: ImportReviewAction,
        company_contact_created: bool,
    ) -> None:
        if entity_type is ImportEntityType.COMPANY:
            self.company_reviews_required = max(0, self.company_reviews_required - 1)
            if action is ImportReviewAction.MERGE:
                self.companies_reused += 1
            elif action is ImportReviewAction.KEEP_SEPARATE:
                self.companies_created += 1
        elif action is ImportReviewAction.MERGE:
            self.contacts_reused += 1
        elif action is ImportReviewAction.KEEP_SEPARATE:
            self.contacts_created += 1
        if company_contact_created:
            self.company_contacts_created += 1
        self.updated_at = utcnow()

    def pause_for_retry(self) -> None:
        if self.status is ImportResolutionStatus.RUNNING:
            self.status = ImportResolutionStatus.PENDING
            self.updated_at = utcnow()

    def complete(self) -> None:
        if self.status in {ImportResolutionStatus.COMPLETED, ImportResolutionStatus.PARTIAL_FAILED}:
            return
        if self.status is not ImportResolutionStatus.RUNNING:
            raise InvalidStateTransition("only running resolution can complete")
        now = utcnow()
        self.status = (
            ImportResolutionStatus.PARTIAL_FAILED
            if self.failed_rows
            else ImportResolutionStatus.COMPLETED
        )
        self.completed_at = now
        self.updated_at = now

    def fail(self, summary: str) -> None:
        clean_summary = summary.strip()
        if not clean_summary:
            raise DomainError("failed import resolution requires a summary")
        now = utcnow()
        self.status = ImportResolutionStatus.FAILED
        self.error_summary = clean_summary
        self.completed_at = now
        self.updated_at = now

    def _validate(self) -> None:
        counts = (
            self.total_rows,
            self.processed_rows,
            self.companies_created,
            self.companies_reused,
            self.company_reviews_required,
            self.contacts_created,
            self.contacts_reused,
            self.company_contacts_created,
            self.invalid_rows,
            self.failed_rows,
        )
        if any(value < 0 for value in counts):
            raise DomainError("import resolution counters cannot be negative")
        if self.processed_rows > self.total_rows:
            raise DomainError("processed rows cannot exceed total rows")


@dataclass(frozen=True)
class CompanyResolutionCandidate:
    company_id: UUID
    canonical_name: str
    normalized_name: str
    normalized_domain: str | None
    normalized_address: str | None
    company_type: str | None
    normalized_phone: str | None


@dataclass(frozen=True)
class ContactIdentityCandidate:
    contact_id: UUID
    display_name: str
    normalized_name: str
    normalized_title: str | None
    emails: tuple[str, ...]
    linkedin_urls: tuple[str, ...]
    company_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class ImportDecisionView:
    decision: ImportEntityDecision
    row_number: int
    source_label: str
    candidate_label: str | None
    #: Relevant source facts for the human review card (masked/non-raw).
    source_facts: dict[str, str] = field(default_factory=dict)
    is_department_contact: bool = False


@dataclass(frozen=True)
class ImportProcessingJob:
    id: UUID
    import_session_id: UUID
    status: ImportJobStatus
    business_key: str
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
    job_type: ImportJobType = ImportJobType.ENTITY_RESOLUTION
    routing_run_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.job_type is ImportJobType.ENTITY_RESOLUTION and self.routing_run_id is not None:
            raise DomainError("entity-resolution jobs cannot reference a routing run")
        if self.job_type is ImportJobType.PROSPECT_ROUTING and self.routing_run_id is None:
            raise DomainError("prospect-routing jobs require a routing run")

    @classmethod
    def create(
        cls,
        *,
        import_session_id: UUID,
        job_type: ImportJobType = ImportJobType.ENTITY_RESOLUTION,
        routing_run_id: UUID | None = None,
        business_key: str | None = None,
        max_attempts: int = 3,
        now: datetime | None = None,
    ) -> "ImportProcessingJob":
        created_at = now or utcnow()
        resolved_business_key = business_key or (
            f"import-resolution:{import_session_id}"
            if job_type is ImportJobType.ENTITY_RESOLUTION
            else f"prospect-routing:{routing_run_id}"
        )
        return cls(
            id=uuid4(),
            import_session_id=import_session_id,
            status=ImportJobStatus.PENDING,
            business_key=resolved_business_key,
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
            job_type=job_type,
            routing_run_id=routing_run_id,
        )

    def lease(
        self, *, owner: str, lease_ttl: timedelta, now: datetime | None = None
    ) -> "ImportProcessingJob":
        leased_at = now or utcnow()
        if self.status is not ImportJobStatus.PENDING:
            raise InvalidStateTransition(f"cannot lease a {self.status.value} import job")
        if self.available_at > leased_at:
            raise InvalidStateTransition("import job is not available yet")
        if not owner.strip() or lease_ttl <= timedelta(0):
            raise DomainError("import job lease requires owner and positive TTL")
        return dataclasses.replace(
            self,
            status=ImportJobStatus.LEASED,
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

    def start(self, *, owner: str, now: datetime | None = None) -> "ImportProcessingJob":
        started_at = now or utcnow()
        self._require_owner(owner)
        if self.status is not ImportJobStatus.LEASED:
            raise InvalidStateTransition(f"cannot start a {self.status.value} import job")
        return dataclasses.replace(
            self,
            status=ImportJobStatus.RUNNING,
            started_at=self.started_at or started_at,
            heartbeat_at=started_at,
            updated_at=started_at,
        )

    def heartbeat(
        self, *, owner: str, lease_ttl: timedelta, now: datetime | None = None
    ) -> "ImportProcessingJob":
        heartbeat_at = now or utcnow()
        self._require_owner(owner)
        if self.status not in {ImportJobStatus.LEASED, ImportJobStatus.RUNNING}:
            raise InvalidStateTransition(f"cannot heartbeat a {self.status.value} import job")
        return dataclasses.replace(
            self,
            heartbeat_at=heartbeat_at,
            lease_expires_at=heartbeat_at + lease_ttl,
            updated_at=heartbeat_at,
        )

    def complete(self, *, owner: str, now: datetime | None = None) -> "ImportProcessingJob":
        completed_at = now or utcnow()
        if self.status is ImportJobStatus.COMPLETED:
            return self
        self._require_owner(owner)
        if self.status not in {ImportJobStatus.LEASED, ImportJobStatus.RUNNING}:
            raise InvalidStateTransition(f"cannot complete a {self.status.value} import job")
        return dataclasses.replace(
            self,
            status=ImportJobStatus.COMPLETED,
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
    ) -> "ImportProcessingJob":
        failed_at = now or utcnow()
        self._require_owner(owner)
        self._require_error(error_code, error_summary)
        if self.status not in {ImportJobStatus.LEASED, ImportJobStatus.RUNNING}:
            raise InvalidStateTransition(f"cannot retry a {self.status.value} import job")
        if self.attempt_count >= self.max_attempts:
            return self.fail(
                owner=owner,
                error_code=error_code,
                error_summary=error_summary,
                now=failed_at,
            )
        return dataclasses.replace(
            self,
            status=ImportJobStatus.PENDING,
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
    ) -> "ImportProcessingJob":
        failed_at = now or utcnow()
        self._require_owner(owner)
        self._require_error(error_code, error_summary)
        return dataclasses.replace(
            self,
            status=ImportJobStatus.FAILED,
            lease_owner=None,
            lease_acquired_at=None,
            lease_expires_at=None,
            heartbeat_at=failed_at,
            last_error_code=error_code.strip(),
            last_error_summary=error_summary.strip(),
            completed_at=failed_at,
            updated_at=failed_at,
        )

    def recover_stale(self, *, now: datetime | None = None) -> "ImportProcessingJob":
        recovered_at = now or utcnow()
        if self.status not in {ImportJobStatus.LEASED, ImportJobStatus.RUNNING}:
            raise InvalidStateTransition(f"cannot recover a {self.status.value} import job")
        if self.lease_expires_at is None or self.lease_expires_at >= recovered_at:
            raise InvalidStateTransition("import job lease has not expired")
        next_status = (
            ImportJobStatus.FAILED
            if self.attempt_count >= self.max_attempts
            else ImportJobStatus.PENDING
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
            last_error_summary="worker lease expired before import processing completed",
            recovery_count=self.recovery_count + 1,
            last_recovered_at=recovered_at,
            completed_at=recovered_at if next_status is ImportJobStatus.FAILED else None,
            updated_at=recovered_at,
        )

    def reconcile_completed_after_recovery(
        self, *, now: datetime | None = None
    ) -> "ImportProcessingJob":
        recovered_at = now or utcnow()
        if self.lease_expires_at is None or self.lease_expires_at >= recovered_at:
            raise InvalidStateTransition("import job lease has not expired")
        return dataclasses.replace(
            self,
            status=ImportJobStatus.COMPLETED,
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
            raise InvalidStateTransition("import job lease owner does not match")

    @staticmethod
    def _require_error(error_code: str, error_summary: str) -> None:
        if not error_code.strip() or not error_summary.strip():
            raise DomainError("import job error requires a code and summary")
