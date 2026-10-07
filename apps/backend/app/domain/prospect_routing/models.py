"""Framework-free state for deterministic pre-score and sales routing."""

import dataclasses
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from app.domain.clock import utcnow
from app.domain.exceptions import DomainError, InvalidStateTransition

ROUTING_RULES_VERSION = "real-routing-v1.1"


class ProspectRoutingRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_COMPLETED = "partial_completed"
    FAILED = "failed"


class ProspectTier(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class ProspectRouteReviewStatus(StrEnum):
    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    OVERRIDDEN = "overridden"
    BLOCKED = "blocked"


class ProspectRouteReviewAction(StrEnum):
    CONFIRM = "confirm"
    OVERRIDE = "override"
    EXCLUDE = "exclude"


@dataclass(frozen=True)
class ProspectRoutingCriteria:
    target_product_keywords: tuple[str, ...]
    target_hs_codes: tuple[str, ...]
    preferred_origin_countries: tuple[str, ...]
    preferred_pol: tuple[str, ...]
    preferred_pod: tuple[str, ...]
    campaign_name: str | None
    notes: str | None

    def __post_init__(self) -> None:
        if not self.target_product_keywords and not self.target_hs_codes:
            raise DomainError("routing criteria require product keywords or HS codes")

    def to_json(self) -> dict[str, Any]:
        return {
            "target_product_keywords": list(self.target_product_keywords),
            "target_hs_codes": list(self.target_hs_codes),
            "preferred_origin_countries": list(self.preferred_origin_countries),
            "preferred_pol": list(self.preferred_pol),
            "preferred_pod": list(self.preferred_pod),
            "campaign_name": self.campaign_name,
            "notes": self.notes,
        }

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "ProspectRoutingCriteria":
        return cls(
            target_product_keywords=_string_tuple(value.get("target_product_keywords")),
            target_hs_codes=_string_tuple(value.get("target_hs_codes")),
            preferred_origin_countries=_string_tuple(value.get("preferred_origin_countries")),
            preferred_pol=_string_tuple(value.get("preferred_pol")),
            preferred_pod=_string_tuple(value.get("preferred_pod")),
            campaign_name=_optional_string(value.get("campaign_name")),
            notes=_optional_string(value.get("notes")),
        )


class ProspectRoutingRun:
    def __init__(
        self,
        *,
        id: UUID,
        import_session_id: UUID,
        rules_version: str,
        configuration_hash: str,
        entity_state_hash: str,
        execution_generation: int,
        criteria_json: dict[str, Any],
        weights_snapshot_json: dict[str, Any],
        status: ProspectRoutingRunStatus,
        total_companies: int,
        routed_companies: int,
        blocked_companies: int,
        tier_a_count: int,
        tier_b_count: int,
        tier_c_count: int,
        tier_d_count: int,
        started_at: datetime | None,
        completed_at: datetime | None,
        error_summary: str | None,
        created_at: datetime,
        updated_at: datetime,
    ) -> None:
        self.id = id
        self.import_session_id = import_session_id
        self.rules_version = rules_version
        self.configuration_hash = configuration_hash
        self.entity_state_hash = entity_state_hash
        self.execution_generation = execution_generation
        self.criteria_json = dict(criteria_json)
        self.weights_snapshot_json = dict(weights_snapshot_json)
        self.status = status
        self.total_companies = total_companies
        self.routed_companies = routed_companies
        self.blocked_companies = blocked_companies
        self.tier_a_count = tier_a_count
        self.tier_b_count = tier_b_count
        self.tier_c_count = tier_c_count
        self.tier_d_count = tier_d_count
        self.started_at = started_at
        self.completed_at = completed_at
        self.error_summary = error_summary
        self.created_at = created_at
        self.updated_at = updated_at
        self._validate()

    @classmethod
    def create(
        cls,
        *,
        import_session_id: UUID,
        rules_version: str,
        configuration_hash: str,
        entity_state_hash: str,
        criteria: ProspectRoutingCriteria,
        weights_snapshot: dict[str, Any],
    ) -> "ProspectRoutingRun":
        now = utcnow()
        return cls(
            id=uuid4(),
            import_session_id=import_session_id,
            rules_version=rules_version,
            configuration_hash=configuration_hash,
            entity_state_hash=entity_state_hash,
            execution_generation=1,
            criteria_json=criteria.to_json(),
            weights_snapshot_json=weights_snapshot,
            status=ProspectRoutingRunStatus.PENDING,
            total_companies=0,
            routed_companies=0,
            blocked_companies=0,
            tier_a_count=0,
            tier_b_count=0,
            tier_c_count=0,
            tier_d_count=0,
            started_at=None,
            completed_at=None,
            error_summary=None,
            created_at=now,
            updated_at=now,
        )

    @property
    def criteria(self) -> ProspectRoutingCriteria:
        return ProspectRoutingCriteria.from_json(self.criteria_json)

    def reset_for_recalculation(self, *, entity_state_hash: str) -> None:
        if not entity_state_hash.strip():
            raise DomainError("routing run entity-state hash must not be empty")
        self.entity_state_hash = entity_state_hash
        self.execution_generation += 1
        self.status = ProspectRoutingRunStatus.PENDING
        self.total_companies = 0
        self.routed_companies = 0
        self.blocked_companies = 0
        self.tier_a_count = 0
        self.tier_b_count = 0
        self.tier_c_count = 0
        self.tier_d_count = 0
        self.started_at = None
        self.completed_at = None
        self.error_summary = None
        self.updated_at = utcnow()

    def start(self) -> None:
        if self.status in {
            ProspectRoutingRunStatus.COMPLETED,
            ProspectRoutingRunStatus.PARTIAL_COMPLETED,
        }:
            return
        if self.status is ProspectRoutingRunStatus.FAILED:
            raise InvalidStateTransition("failed routing run requires recalculation")
        now = utcnow()
        self.status = ProspectRoutingRunStatus.RUNNING
        self.started_at = self.started_at or now
        self.completed_at = None
        self.error_summary = None
        self.updated_at = now

    def pause_for_retry(self) -> None:
        if self.status is ProspectRoutingRunStatus.RUNNING:
            self.status = ProspectRoutingRunStatus.PENDING
            self.updated_at = utcnow()

    def complete(self, routes: tuple["ProspectRoute", ...]) -> None:
        if self.status is not ProspectRoutingRunStatus.RUNNING:
            raise InvalidStateTransition("only a running routing run can complete")
        total = len(routes)
        blocked = sum(route.review_status is ProspectRouteReviewStatus.BLOCKED for route in routes)
        tiers = {
            tier: sum(route.recommended_tier is tier for route in routes)
            for tier in ProspectTier
        }
        now = utcnow()
        self.total_companies = total
        self.blocked_companies = blocked
        self.routed_companies = total - blocked
        self.tier_a_count = tiers[ProspectTier.A]
        self.tier_b_count = tiers[ProspectTier.B]
        self.tier_c_count = tiers[ProspectTier.C]
        self.tier_d_count = tiers[ProspectTier.D]
        self.status = (
            ProspectRoutingRunStatus.PARTIAL_COMPLETED
            if blocked
            else ProspectRoutingRunStatus.COMPLETED
        )
        self.completed_at = now
        self.updated_at = now
        self._validate()

    def fail(self, summary: str) -> None:
        clean_summary = summary.strip()
        if not clean_summary:
            raise DomainError("failed routing run requires a summary")
        now = utcnow()
        self.status = ProspectRoutingRunStatus.FAILED
        self.error_summary = clean_summary
        self.completed_at = now
        self.updated_at = now

    def _validate(self) -> None:
        if not self.rules_version.strip():
            raise DomainError("routing run requires a rules version")
        if len(self.configuration_hash) != 64 or len(self.entity_state_hash) != 64:
            raise DomainError("routing hashes must be SHA-256 hex digests")
        if self.execution_generation < 1:
            raise DomainError("routing execution generation must be positive")
        counts = (
            self.total_companies,
            self.routed_companies,
            self.blocked_companies,
            self.tier_a_count,
            self.tier_b_count,
            self.tier_c_count,
            self.tier_d_count,
        )
        if any(value < 0 for value in counts):
            raise DomainError("routing counters cannot be negative")
        if self.routed_companies + self.blocked_companies != self.total_companies:
            raise DomainError("routed and blocked counters must equal total companies")
        if (
            self.tier_a_count
            + self.tier_b_count
            + self.tier_c_count
            + self.tier_d_count
            != self.routed_companies
        ):
            raise DomainError("tier counters must equal routed companies")


@dataclass(frozen=True)
class ProspectRoute:
    id: UUID
    routing_run_id: UUID
    execution_generation: int
    company_id: UUID
    company_name: str
    pre_score: float
    recommended_tier: ProspectTier | None
    effective_tier: ProspectTier | None
    feature_snapshot_json: dict[str, Any]
    reason_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    review_status: ProspectRouteReviewStatus
    override_reason: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    contact_count: int
    has_usable_contact: bool
    has_usable_email: bool
    preferred_role_category: str | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.execution_generation < 1:
            raise DomainError("prospect route execution generation must be positive")
        if not 0 <= self.pre_score <= 100:
            raise DomainError("pre-score must be within 0-100")
        if not self.company_name.strip():
            raise DomainError("prospect route requires a company name")
        if not self.reason_codes:
            raise DomainError("prospect route requires reason codes")
        if self.contact_count < 0:
            raise DomainError("prospect route contact count cannot be negative")
        if self.review_status is ProspectRouteReviewStatus.BLOCKED:
            if self.recommended_tier is not None or self.effective_tier is not None:
                raise DomainError("blocked prospect routes cannot have a tier")
        elif self.recommended_tier is None or self.effective_tier is None:
            raise DomainError("routed prospects require recommended and effective tiers")

    @classmethod
    def create(
        cls,
        *,
        routing_run_id: UUID,
        execution_generation: int,
        company_id: UUID,
        company_name: str,
        pre_score: float,
        recommended_tier: ProspectTier | None,
        feature_snapshot_json: dict[str, Any],
        reason_codes: tuple[str, ...],
        warning_codes: tuple[str, ...],
        blocked: bool,
        contact_count: int,
        has_usable_contact: bool,
        has_usable_email: bool,
        preferred_role_category: str | None,
    ) -> "ProspectRoute":
        now = utcnow()
        review_status = (
            ProspectRouteReviewStatus.BLOCKED
            if blocked
            else ProspectRouteReviewStatus.SUGGESTED
        )
        return cls(
            id=uuid4(),
            routing_run_id=routing_run_id,
            execution_generation=execution_generation,
            company_id=company_id,
            company_name=company_name.strip(),
            pre_score=pre_score,
            recommended_tier=recommended_tier,
            effective_tier=recommended_tier,
            feature_snapshot_json=dict(feature_snapshot_json),
            reason_codes=reason_codes,
            warning_codes=warning_codes,
            review_status=review_status,
            override_reason=None,
            reviewed_by=None,
            reviewed_at=None,
            contact_count=contact_count,
            has_usable_contact=has_usable_contact,
            has_usable_email=has_usable_email,
            preferred_role_category=preferred_role_category,
            created_at=now,
            updated_at=now,
        )

    def confirm(self, *, reviewed_by: str, now: datetime | None = None) -> "ProspectRoute":
        reviewer = _required_reviewer(reviewed_by)
        if self.review_status is ProspectRouteReviewStatus.CONFIRMED:
            if self.reviewed_by == reviewer:
                return self
            raise InvalidStateTransition("prospect route was already confirmed differently")
        if self.review_status is not ProspectRouteReviewStatus.SUGGESTED:
            raise InvalidStateTransition("prospect route was already reviewed differently")
        reviewed_at = now or utcnow()
        return dataclasses.replace(
            self,
            review_status=ProspectRouteReviewStatus.CONFIRMED,
            reviewed_by=reviewer,
            reviewed_at=reviewed_at,
            updated_at=reviewed_at,
        )

    def override(
        self,
        *,
        effective_tier: ProspectTier,
        override_reason: str,
        reviewed_by: str,
        now: datetime | None = None,
    ) -> "ProspectRoute":
        reason = override_reason.strip()
        reviewer = _required_reviewer(reviewed_by)
        if not reason:
            raise DomainError("prospect route override requires a reason")
        if self.review_status is ProspectRouteReviewStatus.OVERRIDDEN:
            if (
                self.effective_tier is effective_tier
                and self.override_reason == reason
                and self.reviewed_by == reviewer
            ):
                return self
            raise InvalidStateTransition("prospect route was already overridden differently")
        if self.review_status is not ProspectRouteReviewStatus.SUGGESTED:
            raise InvalidStateTransition("prospect route was already reviewed differently")
        reviewed_at = now or utcnow()
        return dataclasses.replace(
            self,
            effective_tier=effective_tier,
            review_status=ProspectRouteReviewStatus.OVERRIDDEN,
            override_reason=reason,
            reviewed_by=reviewer,
            reviewed_at=reviewed_at,
            updated_at=reviewed_at,
        )


@dataclass(frozen=True)
class RoutingContactSnapshot:
    contact_id: UUID
    role_category: str
    seniority: str
    status: str
    has_usable_channel: bool
    has_usable_email: bool
    is_department_contact: bool = False


@dataclass(frozen=True)
class RoutingSourceRow:
    import_entity_decision_id: UUID
    raw_import_row_id: UUID
    row_number: int
    raw_payload: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class RoutingSourceCompany:
    company_id: UUID
    company_name: str
    website: str | None
    profile_domain: str | None
    profile_address: str | None
    profile_company_type: str | None
    rows: tuple[RoutingSourceRow, ...]
    contacts: tuple[RoutingContactSnapshot, ...]
    unresolved_company_conflict: bool


@dataclass(frozen=True)
class RoutingFeatureInput:
    company_id: UUID
    company_name: str
    website: str | None
    profile_domain: str | None
    profile_address: str | None
    profile_company_type: str | None
    product_descriptions: tuple[str, ...]
    hs_codes: tuple[str, ...]
    shipment_dates: tuple[date, ...]
    # Shipment / supplier origin country (产品/供应商来源国). Never drives
    # NON_US_TARGET; used only for source-fact completeness and origin matching.
    origin_countries: tuple[str, ...]
    pols: tuple[str, ...]
    pods: tuple[str, ...]
    source_row_count: int
    contacts: tuple[RoutingContactSnapshot, ...]
    intermediary_signals: tuple[str, ...]
    strong_exclusion: bool
    unresolved_company_conflict: bool
    # V2 (real-routing-v1.1) source facts; None/missing is UNKNOWN, not negative.
    import_amount_raw: str | None = None
    last_import_at: str | None = None
    supplier: tuple[str, ...] = ()
    # Importer company country (进口商所在国家/地区). Unknown is UNKNOWN, not D.
    importer_country: tuple[str, ...] = ()


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    clean = str(value).strip()
    return clean or None


def _required_reviewer(value: str) -> str:
    clean = value.strip()
    if not clean:
        raise DomainError("prospect route review requires a reviewer")
    return clean
