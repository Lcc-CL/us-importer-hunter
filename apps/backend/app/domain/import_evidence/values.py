"""Import evidence value objects and enums."""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4


class ImportEvidenceJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class ValueType(StrEnum):
    OBSERVED = "observed"
    PROVIDER_ESTIMATED = "provider_estimated"
    SYSTEM_ESTIMATED = "system_estimated"
    UNKNOWN = "unknown"


class EntityMatchMethod(StrEnum):
    STRONG = "strong"
    COMPOSITE = "composite"
    FUZZY = "fuzzy"
    MANUAL = "manual"


class EntityMatchStatus(StrEnum):
    AUTO_MATCH = "auto_match"
    NEEDS_REVIEW = "needs_review"
    SEPARATE = "separate"
    MANUALLY_CONFIRMED = "manually_confirmed"
    MANUALLY_REJECTED = "manually_rejected"


class QualityLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class RawImportRecord:
    """One provider record, immutable once stored."""
    provider: str
    provider_record_id: str
    request_id: UUID
    raw_payload_json: str
    raw_payload_hash: str = ""
    fetched_at: datetime = field(default_factory=lambda: datetime.utcnow())
    provider_updated_at: datetime | None = None
    schema_version: str = "v1"
    fixture: bool = False
    synthetic: bool = False

    def __post_init__(self) -> None:
        if not self.raw_payload_hash:
            h = hashlib.sha256(self.raw_payload_json.encode()).hexdigest()
            object.__setattr__(self, "raw_payload_hash", h)


@dataclass(frozen=True)
class NormalizedShipment:
    """One shipment, normalized across providers."""
    id: UUID = field(default_factory=uuid4)
    importer_name: str = ""
    importer_address: str = ""
    shipper_name: str = ""
    shipper_country: str = ""
    country_of_origin: str = ""
    arrival_date: datetime | None = None
    port_of_lading: str = ""
    port_of_discharge: str = ""
    master_bol: str = ""
    house_bol: str = ""
    carrier_scac: str = ""
    vessel: str = ""
    voyage: str = ""
    container_numbers: tuple[str, ...] = ()
    weight_kg: float | None = None
    teu: float | None = None
    hs_codes: tuple[str, ...] = ()
    goods_description_raw: str = ""
    goods_description_normalized: str = ""
    value_amount: float | None = None
    value_type: ValueType = ValueType.UNKNOWN
    provider: str = ""
    provider_record_id: str = ""
    shipment_fingerprint: str = ""
    fingerprint_version: str = ""
    dedupe_status: str = "ok"
    dedupe_method: str = "fingerprint"
    dedupe_reasons: tuple[str, ...] = ()
    container_count: int = 0
    raw_weight: float | None = None
    raw_weight_unit: str = ""
    normalized_weight: float | None = None
    normalized_weight_unit: str = "kg"
    weight_scope: str = "unknown"
    raw_quantity: float | None = None
    normalized_quantity: float | None = None
    parent_shipment_id: UUID | None = None
    normalization_version: str = ""
    raw_record_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        if not self.shipment_fingerprint:
            fp = _compute_fingerprint(
                provider=self.provider,
                master_bol=self.master_bol,
                house_bol=self.house_bol,
                carrier_scac=self.carrier_scac,
                arrival_date=str(self.arrival_date) if self.arrival_date else "",
                vessel=self.vessel,
                voyage=self.voyage,
                normalized_importer=self.importer_name,
                normalized_shipper=self.shipper_name,
                origin_port=self.port_of_lading,
                destination_port=self.port_of_discharge,
                container_numbers=self.container_numbers,
            )
            object.__setattr__(self, "shipment_fingerprint", fp)
            object.__setattr__(self, "fingerprint_version", "shipment-fp-v2")


@dataclass(frozen=True)
class ImporterEntityMatch:
    """Links a normalized shipment to a known Company."""
    id: UUID = field(default_factory=uuid4)
    company_id: UUID | None = None
    normalized_name: str = ""
    match_method: EntityMatchMethod = EntityMatchMethod.FUZZY
    match_score: float = 0.0
    match_reasons: tuple[str, ...] = ()
    candidate_company_ids: tuple[UUID, ...] = ()
    review_status: EntityMatchStatus = EntityMatchStatus.NEEDS_REVIEW
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None


@dataclass(frozen=True)
class ImportEvidenceSignal:
    """Promoted evidence: a company-scored import activity claim."""
    id: UUID = field(default_factory=uuid4)
    company_id: UUID | None = None
    provider: str = ""
    raw_record_ids: tuple[UUID, ...] = ()
    normalized_shipment_ids: tuple[UUID, ...] = ()
    aggregation_window: str = ""
    calculation_method: str = ""
    quality_score: float = 0.0
    quality_level: QualityLevel = QualityLevel.REVIEW
    entity_match_method: EntityMatchMethod = EntityMatchMethod.FUZZY
    entity_match_score: float = 0.0
    promotion_version: str = "v1"


@dataclass(frozen=True)
class ImportEvidenceConflict:
    """When two providers disagree on the same company."""
    id: UUID = field(default_factory=uuid4)
    company_id: UUID | None = None
    signal_ids: tuple[UUID, ...] = ()
    conflict_type: str = ""
    conflict_detail: str = ""
    resolved: bool = False
    resolution_note: str = ""


def _compute_fingerprint(
    *, provider: str = "", master_bol: str = "", house_bol: str = "",
    carrier_scac: str = "", arrival_date: str = "", vessel: str = "",
    voyage: str = "", normalized_importer: str = "", normalized_shipper: str = "",
    origin_port: str = "", destination_port: str = "",
    container_numbers: tuple[str, ...] = (),
) -> str:
    """Versioned, field-labeled, NULL-safe, provider-independent fingerprint.

    Containers are NOT in the fingerprint — they are aggregate attributes
    that may differ across providers for the same business shipment.
    Importer name is stripped of punctuation before hashing so "ACME INC."
    and "ACME, INC" produce the same identity.
    """
    import json
    _null = "__NULL__"

    def _s(v: object) -> str:
        if v is None or v == "":
            return _null
        if isinstance(v, (list, tuple, set)):
            return "|".join(sorted(str(x) for x in v))
        return str(v)

    def _norm_name(raw: str) -> str:
        n = raw.lower().strip()
        n = re.sub(r"[.,;:]+", "", n)
        n = re.sub(r"\s+", " ", n).strip()
        return n

    fields = {
        "v": "shipment-fp-v2",
        "hb": _s(_normalize_bol(house_bol)),
        "mb": _s(_normalize_bol(master_bol)),
        "sc": _s(carrier_scac.upper().strip()[:4]),
        "ad": _s(arrival_date),
        "vs": _s(vessel.upper().strip()),
        "vy": _s(voyage.upper().strip()),
        "ni": _s(_norm_name(normalized_importer)),
        "ns": _s(_norm_name(normalized_shipper)),
        "op": _s(origin_port.upper().strip()),
        "dp": _s(destination_port.upper().strip()),
    }
    canonical = json.dumps(fields, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _normalize_bol(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"[-\s]+", "", raw.upper().strip())


def _normalize_cont(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"[-\s]+", "", raw).upper()


QUALITY_WEIGHTS: dict[str, float] = {
    "source_reliability": 0.30,
    "entity_match_confidence": 0.25,
    "freshness_score": 0.20,
    "record_completeness": 0.15,
    "cross_source_consistency": 0.10,
}
