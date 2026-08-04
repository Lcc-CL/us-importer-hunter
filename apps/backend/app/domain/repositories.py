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

from app.domain.bulk_import import ImportSession, RawImportRow, RawImportRowStatus
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
from app.domain.import_resolution import (
    CompanyContact,
    CompanyExternalIdentity,
    CompanyResolutionCandidate,
    CompanyResolutionProfile,
    ContactIdentityCandidate,
    ImportDecisionView,
    ImportEntityDecision,
    ImportEntityReviewStatus,
    ImportEntityType,
    ImportProcessingJob,
    ImportResolution,
)
from app.domain.opportunity import Opportunity
from app.domain.outreach import Outreach
from app.domain.prospect_batch import ProspectBatch
from app.domain.prospect_job import ProspectJob
from app.domain.prospect_routing import (
    ProspectRoute,
    ProspectRouteReviewStatus,
    ProspectRoutingRun,
    ProspectTier,
    RoutingSourceCompany,
)
from app.domain.research import ResearchRun
from app.domain.task import Task
from app.domain.umail_export import (
    SuppressionEntry,
    UmailExportBatch,
    UmailExportCompanyCandidate,
    UmailExportRow,
)
from app.domain.umail_feedback import (
    ContactEngagementEvent,
    FeedbackExportSnapshot,
    UmailResultImport,
    UmailResultMatchStatus,
    UmailResultRow,
)
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


class BulkImportRepository(Protocol):
    async def get_session(self, session_id: UUID) -> ImportSession | None: ...

    async def find_session(
        self, *, source: str, file_sha256: str
    ) -> ImportSession | None: ...

    async def add_session(self, session: ImportSession) -> None: ...

    async def save_session(self, session: ImportSession) -> None: ...

    async def add_rows(self, rows: tuple[RawImportRow, ...]) -> None: ...

    async def get_row(self, row_id: UUID) -> RawImportRow | None: ...

    async def list_accepted_rows_after(
        self,
        *,
        session_id: UUID,
        after_row_number: int,
        limit: int,
    ) -> list[RawImportRow]: ...

    async def list_rows(
        self,
        *,
        session_id: UUID,
        status: RawImportRowStatus | None,
        offset: int,
        limit: int,
    ) -> tuple[list[RawImportRow], int]: ...

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

    async def find_for_routing_selection(
        self, *, routing_run_id: UUID, routing_selection_hash: str
    ) -> ProspectBatch | None: ...

    async def has_completed_pipeline(
        self,
        *,
        discovery_task_id: UUID,
        company_id: UUID,
        pipeline_version: str,
        exclude_batch_id: UUID | None = None,
    ) -> bool: ...

    async def has_completed_routing_pipeline(
        self,
        *,
        routing_run_id: UUID,
        routing_execution_generation: int,
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


class ImportResolutionRepository(Protocol):
    async def get_resolution(self, session_id: UUID) -> ImportResolution | None: ...

    async def get_resolution_for_update(
        self, session_id: UUID
    ) -> ImportResolution | None: ...

    async def add_resolution(self, resolution: ImportResolution) -> None: ...

    async def save_resolution(self, resolution: ImportResolution) -> None: ...

    async def list_processed_row_ids(self, session_id: UUID) -> set[UUID]: ...

    async def add_decisions(self, decisions: tuple[ImportEntityDecision, ...]) -> None: ...

    async def get_decision(self, decision_id: UUID) -> ImportEntityDecision | None: ...

    async def get_decision_for_update(
        self, decision_id: UUID
    ) -> ImportEntityDecision | None: ...

    async def get_row_decision(
        self,
        *,
        session_id: UUID,
        raw_import_row_id: UUID,
        entity_type: ImportEntityType,
    ) -> ImportEntityDecision | None: ...

    async def save_decision(self, decision: ImportEntityDecision) -> None: ...

    async def list_decisions(
        self,
        *,
        session_id: UUID,
        entity_type: ImportEntityType | None,
        review_status: ImportEntityReviewStatus | None,
        min_confidence: float | None,
        max_confidence: float | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ImportDecisionView], int]: ...

    async def list_company_candidates(self) -> list[CompanyResolutionCandidate]: ...

    async def list_external_identities(self) -> list[CompanyExternalIdentity]: ...

    async def add_external_identity(self, identity: CompanyExternalIdentity) -> None: ...

    async def save_external_identity(self, identity: CompanyExternalIdentity) -> None: ...

    async def update_external_identities(
        self, identities: tuple[CompanyExternalIdentity, ...]
    ) -> None: ...

    async def get_company_profile(
        self, company_id: UUID
    ) -> CompanyResolutionProfile | None: ...

    async def list_company_profiles(self) -> list[CompanyResolutionProfile]: ...

    async def add_company_profile(self, profile: CompanyResolutionProfile) -> None: ...

    async def save_company_profile(self, profile: CompanyResolutionProfile) -> None: ...

    async def update_company_profiles(
        self, profiles: tuple[CompanyResolutionProfile, ...]
    ) -> None: ...

    async def list_contact_candidates(self) -> list[ContactIdentityCandidate]: ...

    async def list_company_contacts(self) -> list[CompanyContact]: ...

    async def add_company_contact(self, link: CompanyContact) -> None: ...

    async def save_company_contact(self, link: CompanyContact) -> None: ...

    async def update_company_contacts(self, links: tuple[CompanyContact, ...]) -> None: ...


class ImportProcessingJobRepository(Protocol):
    async def get_by_id_for_update(
        self, job_id: UUID
    ) -> ImportProcessingJob | None: ...

    async def get_latest_for_session(
        self, session_id: UUID
    ) -> ImportProcessingJob | None: ...

    async def get_latest_for_routing_run(
        self, routing_run_id: UUID
    ) -> ImportProcessingJob | None: ...

    async def find_active_by_business_key(
        self, business_key: str
    ) -> ImportProcessingJob | None: ...

    async def add(self, job: ImportProcessingJob) -> None: ...

    async def save(self, job: ImportProcessingJob) -> None: ...

    async def claim_next(
        self,
        *,
        owner: str,
        now: datetime,
        lease_ttl: timedelta,
    ) -> ImportProcessingJob | None: ...

    async def get_stale_for_update(
        self, *, now: datetime, limit: int
    ) -> list[ImportProcessingJob]: ...


class ProspectRoutingRepository(Protocol):
    async def get_run(self, routing_run_id: UUID) -> ProspectRoutingRun | None: ...

    async def get_run_for_update(
        self, routing_run_id: UUID
    ) -> ProspectRoutingRun | None: ...

    async def find_run_by_configuration(
        self,
        *,
        import_session_id: UUID,
        rules_version: str,
        configuration_hash: str,
    ) -> ProspectRoutingRun | None: ...

    async def add_run(self, run: ProspectRoutingRun) -> None: ...

    async def save_run(self, run: ProspectRoutingRun) -> None: ...

    async def add_routes(self, routes: tuple[ProspectRoute, ...]) -> None: ...

    async def list_available_generations(
        self, routing_run_id: UUID
    ) -> tuple[int, ...]: ...

    async def get_route(self, route_id: UUID) -> ProspectRoute | None: ...

    async def get_route_for_update(self, route_id: UUID) -> ProspectRoute | None: ...

    async def save_route(self, route: ProspectRoute) -> None: ...

    async def list_routes(
        self,
        *,
        routing_run_id: UUID,
        execution_generation: int,
        tier: ProspectTier | None,
        review_status: ProspectRouteReviewStatus | None,
        minimum_score: float | None,
        maximum_score: float | None,
        has_contact: bool | None,
        role_category: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ProspectRoute], int]: ...

    async def list_routes_for_companies(
        self,
        *,
        routing_run_id: UUID,
        execution_generation: int,
        company_ids: tuple[UUID, ...],
    ) -> list[ProspectRoute]: ...

    async def list_source_companies(
        self, import_session_id: UUID
    ) -> tuple[RoutingSourceCompany, ...]: ...


class UmailExportRepository(Protocol):
    async def get_suppression(self, entry_id: UUID) -> SuppressionEntry | None: ...

    async def get_suppression_for_update(
        self, entry_id: UUID
    ) -> SuppressionEntry | None: ...

    async def add_suppression(self, entry: SuppressionEntry) -> None: ...

    async def save_suppression(self, entry: SuppressionEntry) -> None: ...

    async def list_suppressions(
        self, *, active: bool | None, offset: int, limit: int
    ) -> tuple[list[SuppressionEntry], int]: ...

    async def list_active_suppressions(self) -> list[SuppressionEntry]: ...

    async def find_batch_by_selection_hash(
        self, selection_hash: str
    ) -> UmailExportBatch | None: ...

    async def get_batch(self, batch_id: UUID) -> UmailExportBatch | None: ...

    async def get_batch_for_update(self, batch_id: UUID) -> UmailExportBatch | None: ...

    async def add_batch(
        self, batch: UmailExportBatch, rows: tuple[UmailExportRow, ...]
    ) -> None: ...

    async def save_batch(self, batch: UmailExportBatch) -> None: ...

    async def list_rows(self, batch_id: UUID) -> list[UmailExportRow]: ...

    async def load_b_candidates(
        self,
        *,
        routing_run_id: UUID,
        execution_generation: int,
        company_ids: tuple[UUID, ...],
    ) -> tuple[UmailExportCompanyCandidate, ...]: ...


class UmailFeedbackRepository(Protocol):
    async def find_import_by_file_hash(
        self, file_sha256: str
    ) -> UmailResultImport | None: ...

    async def get_import(self, result_import_id: UUID) -> UmailResultImport | None: ...

    async def get_import_for_update(
        self, result_import_id: UUID
    ) -> UmailResultImport | None: ...

    async def add_import(
        self,
        result_import: UmailResultImport,
        rows: tuple[UmailResultRow, ...],
    ) -> None: ...

    async def save_import(self, result_import: UmailResultImport) -> None: ...

    async def list_rows(
        self,
        *,
        result_import_id: UUID,
        match_status: UmailResultMatchStatus | None,
        event_type: str | None,
        campaign: str | None,
        suppression_impact: bool | None,
        offset: int,
        limit: int,
    ) -> tuple[list[UmailResultRow], int]: ...

    async def list_rows_for_apply(
        self, result_import_id: UUID
    ) -> list[UmailResultRow]: ...

    async def load_export_snapshots(
        self,
        *,
        export_row_ids: tuple[UUID, ...],
        emails: tuple[str, ...],
    ) -> tuple[FeedbackExportSnapshot, ...]: ...

    async def existing_event_fingerprints(
        self, fingerprints: tuple[str, ...]
    ) -> set[str]: ...

    async def add_events(self, events: tuple[ContactEngagementEvent, ...]) -> None: ...

    async def list_events(
        self, result_import_id: UUID
    ) -> list[ContactEngagementEvent]: ...


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


class BulkImportUnitOfWork(Protocol):
    bulk_import: BulkImportRepository

    async def __aenter__(self) -> "BulkImportUnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def flush(self) -> None: ...

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
    prospect_routing: ProspectRoutingRepository
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


class ImportResolutionUnitOfWork(Protocol):
    bulk_import: BulkImportRepository
    companies: CompanyRepository
    contacts: ContactRepository
    import_resolution: ImportResolutionRepository
    import_processing_jobs: ImportProcessingJobRepository
    prospect_routing: ProspectRoutingRepository
    prospect_batches: ProspectBatchRepository

    async def __aenter__(self) -> "ImportResolutionUnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def flush(self) -> None: ...

    async def rollback(self) -> None: ...


class UmailExportUnitOfWork(Protocol):
    prospect_routing: ProspectRoutingRepository
    umail_exports: UmailExportRepository

    async def __aenter__(self) -> "UmailExportUnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def flush(self) -> None: ...

    async def rollback(self) -> None: ...


class UmailFeedbackUnitOfWork(Protocol):
    umail_feedback: UmailFeedbackRepository
    umail_exports: UmailExportRepository

    async def __aenter__(self) -> "UmailFeedbackUnitOfWork": ...

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
