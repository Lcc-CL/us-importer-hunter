"""Framework-free state for B-prospect CSV export and suppression."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.exceptions import DomainError, InvalidStateTransition
from app.domain.prospect_routing import ProspectRouteReviewStatus, ProspectTier

UMAIL_EXPORT_MAPPING_VERSION = "umail-export-contract-v1"


class UmailExportBatchStatus(StrEnum):
    PREPARED = "prepared"
    DOWNLOADED = "downloaded"


class UmailExportRowStatus(StrEnum):
    READY = "ready"
    SUPPRESSED = "suppressed"
    INVALID = "invalid"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class SuppressionEntry:
    id: UUID
    email: str | None
    domain: str | None
    company: str | None
    active: bool
    reason: str
    source: str
    created_by: str
    deactivated_by: str | None
    deactivated_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        targets = tuple(value for value in (self.email, self.domain, self.company) if value)
        if len(targets) != 1:
            raise DomainError("suppression entry requires exactly one target")
        if not self.reason.strip() or not self.source.strip() or not self.created_by.strip():
            raise DomainError("suppression entry requires reason, source, and creator")
        if self.active and (self.deactivated_by is not None or self.deactivated_at is not None):
            raise DomainError("active suppression cannot contain deactivation audit")
        if not self.active and (self.deactivated_by is None or self.deactivated_at is None):
            raise DomainError("inactive suppression requires deactivation audit")

    @classmethod
    def create(
        cls,
        *,
        email: str | None,
        domain: str | None,
        company: str | None,
        reason: str,
        source: str,
        created_by: str,
    ) -> "SuppressionEntry":
        normalized_email = _normalize_optional(email)
        normalized_domain = _normalize_optional(domain)
        normalized_company = _normalize_company(company)
        now = utcnow()
        return cls(
            id=uuid4(),
            email=normalized_email,
            domain=normalized_domain.lstrip("@") if normalized_domain else None,
            company=normalized_company,
            active=True,
            reason=reason.strip(),
            source=source.strip(),
            created_by=created_by.strip(),
            deactivated_by=None,
            deactivated_at=None,
            created_at=now,
            updated_at=now,
        )

    def deactivate(self, *, deactivated_by: str) -> "SuppressionEntry":
        actor = deactivated_by.strip()
        if not actor:
            raise DomainError("suppression deactivation requires an actor")
        if not self.active:
            return self
        now = utcnow()
        return SuppressionEntry(
            id=self.id,
            email=self.email,
            domain=self.domain,
            company=self.company,
            active=False,
            reason=self.reason,
            source=self.source,
            created_by=self.created_by,
            deactivated_by=actor,
            deactivated_at=now,
            created_at=self.created_at,
            updated_at=now,
        )


class UmailExportBatch:
    def __init__(
        self,
        *,
        id: UUID,
        routing_run_id: UUID,
        execution_generation: int,
        campaign: str,
        mapping_version: str,
        selection_hash: str,
        status: UmailExportBatchStatus,
        total_rows: int,
        ready_count: int,
        suppressed_count: int,
        invalid_count: int,
        duplicate_count: int,
        content_sha256: str,
        downloaded_at: datetime | None,
        created_at: datetime,
        updated_at: datetime,
    ) -> None:
        self.id = id
        self.routing_run_id = routing_run_id
        self.execution_generation = execution_generation
        self.campaign = campaign
        self.mapping_version = mapping_version
        self.selection_hash = selection_hash
        self.status = status
        self.total_rows = total_rows
        self.ready_count = ready_count
        self.suppressed_count = suppressed_count
        self.invalid_count = invalid_count
        self.duplicate_count = duplicate_count
        self.content_sha256 = content_sha256
        self.downloaded_at = downloaded_at
        self.created_at = created_at
        self.updated_at = updated_at
        self._validate()

    @classmethod
    def prepare(
        cls,
        *,
        id: UUID,
        routing_run_id: UUID,
        execution_generation: int,
        campaign: str,
        mapping_version: str,
        selection_hash: str,
        rows: tuple["UmailExportRow", ...],
        content_sha256: str,
    ) -> "UmailExportBatch":
        now = utcnow()
        counts = {
            status: sum(row.status is status for row in rows)
            for status in UmailExportRowStatus
        }
        return cls(
            id=id,
            routing_run_id=routing_run_id,
            execution_generation=execution_generation,
            campaign=campaign.strip(),
            mapping_version=mapping_version,
            selection_hash=selection_hash,
            status=UmailExportBatchStatus.PREPARED,
            total_rows=len(rows),
            ready_count=counts[UmailExportRowStatus.READY],
            suppressed_count=counts[UmailExportRowStatus.SUPPRESSED],
            invalid_count=counts[UmailExportRowStatus.INVALID],
            duplicate_count=counts[UmailExportRowStatus.DUPLICATE],
            content_sha256=content_sha256,
            downloaded_at=None,
            created_at=now,
            updated_at=now,
        )

    def mark_downloaded(self) -> None:
        if self.status not in {
            UmailExportBatchStatus.PREPARED,
            UmailExportBatchStatus.DOWNLOADED,
        }:
            raise InvalidStateTransition("export batch cannot be downloaded")
        now = utcnow()
        self.status = UmailExportBatchStatus.DOWNLOADED
        self.downloaded_at = self.downloaded_at or now
        self.updated_at = now

    def _validate(self) -> None:
        if self.execution_generation < 1:
            raise DomainError("export execution generation must be positive")
        if not self.campaign.strip() or not self.mapping_version.strip():
            raise DomainError("export batch requires campaign and mapping version")
        if len(self.selection_hash) != 64 or len(self.content_sha256) != 64:
            raise DomainError("export hashes must be SHA-256 hex digests")
        counts = (
            self.ready_count,
            self.suppressed_count,
            self.invalid_count,
            self.duplicate_count,
        )
        if self.total_rows < 0 or any(value < 0 for value in counts):
            raise DomainError("export counts must not be negative")
        if sum(counts) != self.total_rows:
            raise DomainError("export row-status counts must equal total rows")
        if self.status is UmailExportBatchStatus.DOWNLOADED and self.downloaded_at is None:
            raise DomainError("downloaded export batch requires downloaded_at")


@dataclass(frozen=True)
class UmailExportRow:
    id: UUID
    batch_id: UUID
    position: int
    company_id: UUID
    contact_id: UUID | None
    company_name: str
    company_website: str | None
    contact_name: str | None
    contact_title: str | None
    contact_role: str | None
    contact_seniority: str | None
    is_department_contact: bool
    email: str | None
    route: ProspectTier
    route_review_status: ProspectRouteReviewStatus
    pre_score: float
    status: UmailExportRowStatus
    exclusion_reason: str | None
    row_fingerprint: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.position < 1:
            raise DomainError("export row position must be positive")
        if self.route is not ProspectTier.B:
            raise DomainError("Umail export rows must snapshot effective tier B")
        if self.route_review_status not in {
            ProspectRouteReviewStatus.CONFIRMED,
            ProspectRouteReviewStatus.OVERRIDDEN,
        }:
            raise DomainError("Umail export rows require human-confirmed routing")
        if not 0 <= self.pre_score <= 100:
            raise DomainError("export pre-score must be within 0-100")
        if len(self.row_fingerprint) != 64:
            raise DomainError("row fingerprint must be a SHA-256 hex digest")
        if self.status is UmailExportRowStatus.READY and not self.email:
            raise DomainError("ready export row requires an email")
        if self.status is not UmailExportRowStatus.READY and not self.exclusion_reason:
            raise DomainError("excluded export row requires an exclusion reason")

    @classmethod
    def create(
        cls,
        *,
        batch_id: UUID,
        position: int,
        company_id: UUID,
        contact_id: UUID | None,
        company_name: str,
        company_website: str | None,
        contact_name: str | None,
        contact_title: str | None,
        contact_role: str | None,
        contact_seniority: str | None,
        is_department_contact: bool,
        email: str | None,
        route_review_status: ProspectRouteReviewStatus,
        pre_score: float,
        status: UmailExportRowStatus,
        exclusion_reason: str | None,
    ) -> "UmailExportRow":
        payload: dict[str, object] = {
            "company_id": str(company_id),
            "contact_id": str(contact_id) if contact_id else None,
            "company_name": company_name,
            "company_website": company_website,
            "contact_name": contact_name,
            "contact_title": contact_title,
            "contact_role": contact_role,
            "contact_seniority": contact_seniority,
            "is_department_contact": is_department_contact,
            "email": email,
            "route": ProspectTier.B.value,
            "route_review_status": route_review_status.value,
            "pre_score": pre_score,
            "status": status.value,
            "exclusion_reason": exclusion_reason,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return cls(
            id=uuid4(),
            batch_id=batch_id,
            position=position,
            company_id=company_id,
            contact_id=contact_id,
            company_name=company_name,
            company_website=company_website,
            contact_name=contact_name,
            contact_title=contact_title,
            contact_role=contact_role,
            contact_seniority=contact_seniority,
            is_department_contact=is_department_contact,
            email=email,
            route=ProspectTier.B,
            route_review_status=route_review_status,
            pre_score=pre_score,
            status=status,
            exclusion_reason=exclusion_reason,
            row_fingerprint=fingerprint,
            created_at=utcnow(),
        )


@dataclass(frozen=True)
class UmailExportEmailCandidate:
    normalized_value: str
    display_value: str
    verification_status: str


@dataclass(frozen=True)
class UmailExportContactCandidate:
    contact_id: UUID
    name: str
    title: str | None
    role_category: str
    seniority: str
    is_department_contact: bool
    emails: tuple[UmailExportEmailCandidate, ...]


@dataclass(frozen=True)
class UmailExportCompanyCandidate:
    company_id: UUID
    company_name: str
    company_website: str | None
    pre_score: float
    effective_tier: ProspectTier | None
    review_status: ProspectRouteReviewStatus
    contacts: tuple[UmailExportContactCandidate, ...]


def normalize_suppression_company(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    clean = value.strip().casefold()
    return clean or None


def _normalize_company(value: str | None) -> str | None:
    if value is None:
        return None
    clean = normalize_suppression_company(value)
    return clean or None
