"""Repository and Unit of Work protocols — the domain's persistence ports.

Interfaces speak domain aggregates only; SQLAlchemy implementations live
in app/database/repositories and must never leak ORM models through
these signatures (enforced by tests). Operations are aggregate-oriented:
no generic CRUD base (ADR-0010/0017).
"""

from datetime import datetime, timedelta
from types import TracebackType
from typing import Protocol
from uuid import UUID

from app.domain.company import Company
from app.domain.contact import Contact, DecisionMakerFitAssessment
from app.domain.discovery import DiscoveryTask
from app.domain.import_evidence.models import (
    ImporterEvidenceAggregate,
    ImportEvidenceCompanySignal,
    ImportEvidenceSignalPromotion,
    QualityAssessment,
    ShipmentInclusion,
    SignalPromotionCandidate,
)
from app.domain.import_evidence.values import (
    ImporterEntityMatch,
    NormalizedShipment,
    RawImportRecord,
)
from app.domain.opportunity import Opportunity
from app.domain.outreach import Outreach
from app.domain.prospect_batch import ProspectBatch
from app.domain.prospect_job import ProspectJob
from app.domain.research import ResearchRun
from app.domain.task import Task
from app.domain.values import CompanyName, IdempotencyKey


class CompanyRepository(Protocol):
    async def get_by_id(self, company_id: UUID) -> Company | None: ...

    async def add(self, company: Company) -> None: ...

    async def save(self, company: Company) -> None: ...

    async def exists(self, company_id: UUID) -> bool: ...

    async def find_by_normalized_name(self, name: CompanyName) -> Company | None:
        """Dedup lookup: the canonical company already using this name, if any."""
        ...

    async def find_by_website_host(self, host: str) -> Company | None:
        """Dedup lookup: the canonical company already using this web host, if any."""
        ...


class OpportunityRepository(Protocol):
    async def get_by_id(self, opportunity_id: UUID) -> Opportunity | None: ...

    async def add(self, opportunity: Opportunity) -> None: ...

    async def save(self, opportunity: Opportunity) -> None: ...

    async def get_for_company_and_user(self, company_id: UUID, user_id: UUID) -> Opportunity | None:
        """The judgment this user currently holds about this company:
        the open opportunity if one exists, else the most recent one."""
        ...


class OutreachRepository(Protocol):
    async def get_by_id(self, outreach_id: UUID) -> Outreach | None: ...

    async def add(self, outreach: Outreach) -> None: ...

    async def save(self, outreach: Outreach) -> None: ...

    async def list_for_opportunity(self, opportunity_id: UUID) -> list[Outreach]: ...


class ContactRepository(Protocol):
    async def get_by_id(self, contact_id: UUID) -> Contact | None: ...

    async def add(self, contact: Contact) -> None: ...

    async def save(self, contact: Contact) -> None: ...

    async def list_for_company(self, company_id: UUID) -> list[Contact]: ...

    async def find_by_email(self, company_id: UUID, normalized_email: str) -> Contact | None:
        """Dedup lookup: strong match on a company-scoped email channel."""
        ...

    async def find_by_linkedin_url(self, company_id: UUID, normalized_url: str) -> Contact | None:
        """Dedup lookup: strong match on a company-scoped LinkedIn channel."""
        ...

    async def record_fit_assessment(self, assessment: DecisionMakerFitAssessment) -> None:
        """Append-only; duplicates rejected by (contact_id, fingerprint)."""
        ...

    async def list_fit_assessments_for_company(
        self, company_id: UUID
    ) -> list[DecisionMakerFitAssessment]:
        """Persisted decision-maker judgments for the MVP prospect read model."""
        ...


class TaskRepository(Protocol):
    async def get_by_id(self, task_id: UUID) -> Task | None: ...

    async def add(self, task: Task) -> None: ...

    async def save(self, task: Task) -> None: ...

    async def active_keys(self) -> set[IdempotencyKey]:
        """Idempotency keys of currently active (created/running) tasks —
        feeds Task.create's duplicate protection."""
        ...


class DiscoveryTaskRepository(Protocol):
    async def get_by_id(self, task_id: UUID) -> DiscoveryTask | None: ...

    async def add(self, task: DiscoveryTask) -> None: ...

    async def save(self, task: DiscoveryTask) -> None: ...


class ProspectBatchRepository(Protocol):
    async def get_by_id(self, batch_id: UUID) -> ProspectBatch | None: ...

    async def get_by_id_for_update(self, batch_id: UUID) -> ProspectBatch | None: ...

    async def add(self, batch: ProspectBatch) -> None: ...

    async def save(self, batch: ProspectBatch) -> None: ...

    async def has_completed_pipeline(
        self,
        *,
        discovery_task_id: UUID,
        company_id: UUID,
        pipeline_version: str,
        exclude_batch_id: UUID | None = None,
    ) -> bool: ...


class ProspectJobRepository(Protocol):
    async def get_by_id(self, job_id: UUID) -> ProspectJob | None: ...

    async def get_by_id_for_update(self, job_id: UUID) -> ProspectJob | None: ...

    async def get_latest_for_batch(self, batch_id: UUID) -> ProspectJob | None: ...

    async def find_by_request_key_hash(self, request_key_hash: str) -> ProspectJob | None: ...

    async def find_active_by_business_key(self, business_key: str) -> ProspectJob | None: ...

    async def add(self, job: ProspectJob) -> None: ...

    async def save(self, job: ProspectJob) -> None: ...

    async def claim_next(
        self,
        *,
        owner: str,
        now: datetime,
        lease_ttl: timedelta,
    ) -> ProspectJob | None: ...

    async def get_stale_for_update(
        self, *, now: datetime, limit: int
    ) -> list[ProspectJob]: ...


class ResearchRunRepository(Protocol):
    """Persistence for research runs (v0.2). A run is an audit record of what
    a website claimed and what a human decided — never company state."""

    async def get_by_id(self, research_id: UUID) -> "ResearchRun | None": ...

    async def add(self, run: "ResearchRun") -> None: ...

    async def save(self, run: "ResearchRun") -> None: ...

    async def list_for_company(
        self, company_id: UUID, *, limit: int = 20
    ) -> "list[ResearchRun]": ...

    async def list_for_website(self, website: str, *, limit: int = 10) -> "list[ResearchRun]": ...


class ImportEvidenceRepository(Protocol):
    """Versioned persistence for customs quality and importer aggregates."""

    async def save_quality_assessment(
        self, assessment: QualityAssessment
    ) -> tuple[QualityAssessment, bool]: ...

    async def get_current_quality_assessment(
        self, normalized_shipment_id: UUID
    ) -> QualityAssessment | None: ...

    async def list_quality_assessment_history(
        self, normalized_shipment_id: UUID
    ) -> list[QualityAssessment]: ...

    async def save_aggregate(
        self, aggregate: ImporterEvidenceAggregate
    ) -> tuple[ImporterEvidenceAggregate, bool]: ...

    async def get_aggregate_by_id(self, aggregate_id: UUID) -> ImporterEvidenceAggregate | None: ...

    async def get_current_aggregate(
        self, importer_identity: str, window_days: int
    ) -> ImporterEvidenceAggregate | None: ...

    async def list_aggregate_history(
        self, importer_identity: str, window_days: int
    ) -> list[ImporterEvidenceAggregate]: ...

    async def list_aggregate_shipments(self, aggregate_id: UUID) -> list[ShipmentInclusion]: ...

    async def create_upload_job(
        self, company_id: UUID, provider_name: str, request_id: UUID
    ) -> UUID: ...

    async def save_upload_record(self, job_id: UUID, record: RawImportRecord) -> UUID: ...

    async def save_normalized_shipment(
        self, job_id: UUID, shipment: NormalizedShipment, raw_record_id: UUID
    ) -> tuple[UUID, bool]: ...

    async def save_entity_match(self, shipment_id: UUID, match: ImporterEntityMatch) -> None: ...

    async def finish_upload_job(
        self,
        job_id: UUID,
        *,
        status: str,
        total_raw: int,
        total_normalized: int,
        total_deduped: int,
        total_matched: int,
        total_promoted: int,
        error_message: str | None = None,
    ) -> None: ...

    async def get_latest_upload_job(
        self, company_id: UUID
    ) -> tuple[UUID, str, int, int, int, int, int] | None: ...

    async def get_current_aggregate_for_company(
        self, company_id: UUID
    ) -> ImporterEvidenceAggregate | None: ...


class ImportEvidencePromotionRepository(Protocol):
    async def get_quality_assessments(
        self, quality_assessment_ids: tuple[UUID, ...]
    ) -> list[QualityAssessment]: ...

    async def apply_candidates(
        self, candidates: tuple[SignalPromotionCandidate, ...]
    ) -> tuple[list[ImportEvidenceSignalPromotion], bool]: ...

    async def get_promotion_by_id(
        self, promotion_id: UUID
    ) -> ImportEvidenceSignalPromotion | None: ...

    async def list_current_promotions(
        self, company_id: UUID
    ) -> list[ImportEvidenceSignalPromotion]: ...

    async def list_promotion_history(
        self, *, company_id: UUID | None = None, aggregate_id: UUID | None = None
    ) -> list[ImportEvidenceSignalPromotion]: ...

    async def list_active_signals(self, company_id: UUID) -> list[ImportEvidenceCompanySignal]: ...


class ImportEvidenceUnitOfWork(Protocol):
    import_evidence: ImportEvidenceRepository
    import_evidence_promotions: ImportEvidencePromotionRepository

    async def __aenter__(self) -> "ImportEvidenceUnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class DiscoveryTaskUnitOfWork(Protocol):
    """Persistence ports used by the D1 discovery-task supervisor."""

    tasks: TaskRepository
    discovery_tasks: DiscoveryTaskRepository

    async def __aenter__(self) -> "DiscoveryTaskUnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def flush(self) -> None: ...

    async def rollback(self) -> None: ...


class ProspectBatchUnitOfWork(Protocol):
    companies: CompanyRepository
    discovery_tasks: DiscoveryTaskRepository
    prospect_batches: ProspectBatchRepository
    prospect_jobs: ProspectJobRepository
    research_runs: ResearchRunRepository

    async def __aenter__(self) -> "ProspectBatchUnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def flush(self) -> None: ...

    async def rollback(self) -> None: ...


class UnitOfWork(Protocol):
    """One transaction per application use case (ADR-0017)."""

    companies: CompanyRepository
    opportunities: OpportunityRepository
    outreaches: OutreachRepository
    contacts: ContactRepository
    tasks: TaskRepository
    research_runs: ResearchRunRepository

    async def __aenter__(self) -> "UnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
