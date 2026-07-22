"""Persistent domain records for import-evidence quality and aggregation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class QualityStatus(StrEnum):
    VERIFIED = "VERIFIED"
    USABLE = "USABLE"
    REVIEW = "REVIEW"
    REJECTED = "REJECTED"


class AggregateStatus(StrEnum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    BLOCKED = "BLOCKED"


class InclusionStatus(StrEnum):
    TRUSTED = "trusted"
    REVIEW = "review"
    REJECTED = "rejected"
    UNDATED = "undated"
    SKIPPED = "skipped"


class PromotionStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    PROMOTED = "PROMOTED"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class QualityAssessment:
    id: UUID = field(default_factory=uuid4)
    normalized_shipment_id: UUID | None = None
    assessment_version: str = "import-evidence-quality-v1"
    total_score: float = 0.0
    quality_status: QualityStatus = QualityStatus.REJECTED
    source_reliability_score: float = 0.0
    entity_resolution_score: float = 0.0
    identity_completeness_score: float = 0.0
    cross_source_consistency_score: float = 0.0
    freshness_score: float = 0.0
    penalties: tuple[str, ...] = ()
    hard_blockers: tuple[str, ...] = ()
    score_breakdown: dict[str, float] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    input_fingerprint: str = ""
    is_current: bool = True
    assessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    superseded_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.score_breakdown:
            object.__setattr__(
                self,
                "score_breakdown",
                {
                    "source_reliability": self.source_reliability_score,
                    "entity_resolution": self.entity_resolution_score,
                    "identity_completeness": self.identity_completeness_score,
                    "cross_source_consistency": self.cross_source_consistency_score,
                    "freshness": self.freshness_score,
                },
            )

    @property
    def shipment_id(self) -> UUID | None:
        """Compatibility alias used by the original Stage 4A.4.1 tests."""
        return self.normalized_shipment_id


@dataclass(frozen=True)
class ShipmentInclusion:
    normalized_shipment_id: UUID
    quality_assessment_id: UUID | None
    shipment_fingerprint: str
    inclusion_status: InclusionStatus
    inclusion_reason: str
    source_provider_count: int
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def shipment_id(self) -> UUID:
        return self.normalized_shipment_id


@dataclass(frozen=True)
class ImporterEvidenceAggregate:
    id: UUID = field(default_factory=uuid4)
    company_id: UUID | None = None
    importer_identity: str = ""
    aggregate_version: str = "importer-evidence-aggregate-v1"
    rule_version: str = "importer-evidence-aggregate-rules-v1"
    status: AggregateStatus = AggregateStatus.INSUFFICIENT_DATA
    promotable: bool = False
    input_fingerprint: str = ""
    is_current: bool = True
    as_of_date: date = field(default_factory=date.today)
    window_days: int = 365
    previous_window_days: int = 365
    metrics_json: dict[str, Any] = field(default_factory=dict)
    quality_summary_json: dict[str, Any] = field(default_factory=dict)
    blocking_reasons: tuple[str, ...] = ()
    source_provider_count: int = 0
    trusted_shipment_count: int = 0
    verified_shipment_count: int = 0
    usable_shipment_count: int = 0
    review_shipment_count: int = 0
    rejected_shipment_count: int = 0
    undated_shipment_count: int = 0
    skipped_shipment_count: int = 0
    active_month_count: int = 0
    unique_supplier_count: int = 0
    unknown_supplier_count: int = 0
    unique_origin_country_count: int = 0
    unique_destination_port_count: int = 0
    unique_carrier_count: int = 0
    earliest_arrival_date: date | None = None
    latest_arrival_date: date | None = None
    known_origin_shipment_count: int = 0
    china_origin_shipment_count: int = 0
    unknown_origin_shipment_count: int = 0
    total_container_count: int = 0
    known_weight_kg: float | None = None
    shipment_count_90d: int = 0
    shipment_count_365d: int = 0
    shipment_count_730d: int = 0
    shipment_count_previous_365d: int = 0
    median_days_between_shipments: float | None = None
    trend_candidate: str = "insufficient_data"
    status_reasons: tuple[str, ...] = ()
    inclusions: tuple[ShipmentInclusion, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    superseded_at: datetime | None = None


@dataclass(frozen=True)
class SignalPromotionCandidate:
    aggregate_id: UUID
    company_id: UUID | None
    signal_kind: str
    signal_detail: str
    normalized_value_json: dict[str, Any]
    source_summary_json: dict[str, Any]
    evidence_snapshot_json: dict[str, Any]
    quality_status: QualityStatus | None
    quality_score: float | None
    promotion_version: str
    input_fingerprint: str
    status: PromotionStatus
    quality_assessment_ids: tuple[UUID, ...] = ()
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImportEvidenceCompanySignal:
    id: UUID = field(default_factory=uuid4)
    promotion_id: UUID | None = None
    aggregate_id: UUID | None = None
    company_id: UUID | None = None
    signal_kind: str = ""
    signal_detail: str = ""
    normalized_value_json: dict[str, Any] = field(default_factory=dict)
    provenance_json: dict[str, Any] = field(default_factory=dict)
    quality_status: QualityStatus = QualityStatus.REJECTED
    quality_score: float = 0.0
    ownership: str = "import_evidence"
    is_active: bool = True
    superseded_by_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    superseded_at: datetime | None = None

    @property
    def rendered_signal(self) -> str:
        return f"{self.signal_kind}: {self.signal_detail}"


@dataclass(frozen=True)
class ImportEvidenceSignalPromotion:
    id: UUID = field(default_factory=uuid4)
    aggregate_id: UUID | None = None
    company_id: UUID | None = None
    signal_kind: str = ""
    signal_detail: str = ""
    normalized_value_json: dict[str, Any] = field(default_factory=dict)
    source_summary_json: dict[str, Any] = field(default_factory=dict)
    evidence_snapshot_json: dict[str, Any] = field(default_factory=dict)
    quality_status: QualityStatus | None = None
    quality_score: float | None = None
    promotion_version: str = "import-evidence-signal-promotion-v1"
    input_fingerprint: str = ""
    status: PromotionStatus = PromotionStatus.CANDIDATE
    is_current: bool = True
    promoted_signal_id: UUID | None = None
    superseded_by_id: UUID | None = None
    quality_assessment_ids: tuple[UUID, ...] = ()
    rejection_reasons: tuple[str, ...] = ()
    promoted_at: datetime | None = None
    superseded_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ImportEvidenceScoringProjection:
    signals: tuple[ImportEvidenceCompanySignal, ...] = ()
    research_signals: tuple[str, ...] = ()


def stable_fingerprint(payload: dict[str, Any]) -> str:
    """SHA-256 over canonical JSON; callers supply only business identity fields."""
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_default,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"unsupported fingerprint value: {type(value).__name__}")
