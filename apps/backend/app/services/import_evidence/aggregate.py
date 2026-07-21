"""Deterministic importer aggregate with auditable shipment inclusion."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from app.domain.import_evidence.models import (
    AggregateStatus,
    ImporterEvidenceAggregate,
    InclusionStatus,
    ShipmentInclusion,
    stable_fingerprint,
)

AGGREGATE_VERSION = "importer-evidence-aggregate-v1"
AGGREGATE_RULE_VERSION = "importer-evidence-aggregate-rules-v1"
_TRUSTED_QUALITY = frozenset({"VERIFIED", "USABLE"})
_ALLOWED_ENTITY = frozenset({"auto_match", "manually_confirmed", "needs_review"})
_REJECTED_ENTITY = frozenset({"separate", "rejected", "manually_rejected", "unresolved"})

__all__ = [
    "AGGREGATE_RULE_VERSION",
    "AGGREGATE_VERSION",
    "AggregateShipmentInput",
    "AggregateStatus",
    "ImporterEvidenceAggregate",
    "InclusionStatus",
    "ShipmentInclusion",
    "compute_aggregate",
    "normalize_importer_identity",
]


@dataclass(frozen=True)
class AggregateShipmentInput:
    normalized_shipment_id: UUID
    shipment_fingerprint: str
    quality_assessment_id: UUID | None = None
    quality_fingerprint: str = ""
    quality_status: str = "REJECTED"
    quality_hard_blockers: tuple[str, ...] = ()
    dedupe_status: str = "ok"
    entity_match_status: str = "auto_match"
    importer_identity: str = ""
    arrival_date: date | datetime | None = None
    origin: str = ""
    supplier: str = ""
    containers: tuple[str, ...] = ()
    weight_kg: float | None = None
    carrier: str = ""
    port: str = ""
    source_provider_count: int = 1
    source_providers: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> AggregateShipmentInput:
        shipment_id = value.get("normalized_shipment_id", value.get("id"))
        if not isinstance(shipment_id, UUID):
            shipment_id = uuid4()
        raw_date = value.get("arrival_date")
        arrival = raw_date if isinstance(raw_date, (date, datetime)) else None
        containers = tuple(str(item) for item in (value.get("containers") or ()))
        return cls(
            normalized_shipment_id=shipment_id,
            shipment_fingerprint=str(value.get("shipment_fingerprint") or ""),
            quality_assessment_id=_uuid_or_none(value.get("quality_assessment_id")),
            quality_fingerprint=str(value.get("quality_fingerprint") or ""),
            quality_status=str(value.get("quality_status", value.get("quality", "REJECTED"))),
            quality_hard_blockers=tuple(
                str(item) for item in (value.get("quality_hard_blockers") or ())
            ),
            dedupe_status=str(value.get("dedupe_status") or "ok"),
            entity_match_status=str(value.get("entity_match_status") or "auto_match"),
            importer_identity=str(value.get("importer_identity") or ""),
            arrival_date=arrival,
            origin=str(value.get("origin") or ""),
            supplier=str(value.get("supplier") or ""),
            containers=containers,
            weight_kg=_float_or_none(value.get("weight_kg")),
            carrier=str(value.get("carrier") or ""),
            port=str(value.get("port") or ""),
            source_provider_count=max(int(value.get("source_provider_count") or 1), 1),
            source_providers=tuple(
                sorted(
                    str(item)
                    for item in (
                        value.get("source_providers")
                        or ((value.get("provider"),) if value.get("provider") else ())
                    )
                )
            ),
        )


def compute_aggregate(
    *,
    company_id: UUID | None,
    shipments: Sequence[AggregateShipmentInput | Mapping[str, Any]],
    importer_identity: str = "",
    window_days: int = 365,
    previous_window_days: int = 365,
    as_of_date: date | None = None,
    rule_version: str = AGGREGATE_RULE_VERSION,
) -> ImporterEvidenceAggregate:
    """Build one immutable aggregate version from current shipment quality."""
    if window_days <= 0 or previous_window_days <= 0:
        raise ValueError("aggregate windows must be positive")

    reference_date = as_of_date or date.today()
    canonical_identity = normalize_importer_identity(importer_identity)
    inputs = [
        item
        if isinstance(item, AggregateShipmentInput)
        else AggregateShipmentInput.from_mapping(item)
        for item in shipments
    ]
    deduped = _deduplicate_shipments(inputs)

    blocking_reasons: list[str] = []
    partial_reasons: list[str] = []
    included: list[AggregateShipmentInput] = []
    inclusions: list[ShipmentInclusion] = []

    for shipment in deduped:
        entity_status = shipment.entity_match_status.lower().strip()
        shipment_identity = normalize_importer_identity(shipment.importer_identity)
        if shipment.dedupe_status.lower().strip() == "insufficient_identity":
            blocking_reasons.append("insufficient_identity")
            inclusions.append(
                _inclusion(shipment, InclusionStatus.SKIPPED, "insufficient_identity")
            )
            continue
        if shipment.quality_hard_blockers:
            blocking_reasons.extend(shipment.quality_hard_blockers)
            inclusions.append(
                _inclusion(shipment, InclusionStatus.REJECTED, "quality_hard_blocker")
            )
            continue
        if canonical_identity and shipment_identity and shipment_identity != canonical_identity:
            blocking_reasons.append("importer_identity_conflict")
            continue
        if entity_status in _REJECTED_ENTITY or entity_status not in _ALLOWED_ENTITY:
            blocking_reasons.append(f"entity_{entity_status or 'unresolved'}")
            continue

        shipment_date = _business_date(shipment.arrival_date)
        if shipment_date is not None and shipment_date > reference_date:
            blocking_reasons.append("future_arrival_date")
            inclusions.append(_inclusion(shipment, InclusionStatus.REJECTED, "future_arrival_date"))
            continue

        included.append(shipment)
        quality = shipment.quality_status.upper()
        if entity_status == "needs_review":
            partial_reasons.append("entity_needs_review")
        if quality in _TRUSTED_QUALITY:
            status = InclusionStatus.TRUSTED if shipment_date else InclusionStatus.UNDATED
            reason = "quality_trusted" if shipment_date else "trusted_but_undated"
        elif quality == "REVIEW":
            status = InclusionStatus.REVIEW
            reason = "quality_requires_review"
            partial_reasons.append("quality_requires_review")
        else:
            status = InclusionStatus.REJECTED
            reason = "quality_rejected"
        inclusions.append(_inclusion(shipment, status, reason))

    trusted = [s for s in included if s.quality_status.upper() in _TRUSTED_QUALITY]
    review_shipments = [s for s in included if s.quality_status.upper() == "REVIEW"]
    rejected_shipments = [
        s for s in included if s.quality_status.upper() not in _TRUSTED_QUALITY | {"REVIEW"}
    ]
    dated: list[tuple[AggregateShipmentInput, date]] = []
    for shipment in trusted:
        arrival = _business_date(shipment.arrival_date)
        if arrival is not None:
            dated.append((shipment, arrival))
    undated_count = len(trusted) - len(dated)
    if undated_count:
        partial_reasons.append("trusted_shipments_missing_arrival_date")

    current_start = _start_for_window(reference_date, window_days)
    previous_end = current_start - timedelta(days=1)
    previous_start = _start_for_window(previous_end, previous_window_days)
    count_90 = _window_count(dated, _start_for_window(reference_date, 90), reference_date)
    count_365 = _window_count(dated, _start_for_window(reference_date, 365), reference_date)
    count_730 = _window_count(dated, _start_for_window(reference_date, 730), reference_date)
    count_previous = _window_count(dated, previous_start, previous_end)

    suppliers = {s.supplier.strip().lower() for s in trusted if s.supplier.strip()}
    origins = {s.origin.strip().upper() for s in trusted if s.origin.strip()}
    ports = {s.port.strip().upper() for s in trusted if s.port.strip()}
    carriers = {s.carrier.strip().upper() for s in trusted if s.carrier.strip()}
    known_origins = [s for s in trusted if s.origin.strip()]
    china_count = sum(1 for s in known_origins if s.origin.strip().upper() == "CN")
    dates = sorted(d for _, d in dated)
    months = {(d.year, d.month) for d in dates}
    median_days = _median_gap(dates)
    total_containers = sum(
        len({_normalize_container(c) for c in s.containers if c.strip()}) for s in trusted
    )
    weights = [s.weight_kg for s in trusted if s.weight_kg is not None]
    known_weight = sum(weights) if weights else None
    trend = _trend(count_365, count_previous)

    if blocking_reasons:
        aggregate_status = AggregateStatus.BLOCKED
    elif not trusted:
        aggregate_status = AggregateStatus.INSUFFICIENT_DATA
    elif partial_reasons or rejected_shipments:
        aggregate_status = AggregateStatus.PARTIAL
    else:
        aggregate_status = AggregateStatus.READY

    if company_id is None:
        partial_reasons.append("company_not_resolved")
        if aggregate_status is AggregateStatus.READY:
            aggregate_status = AggregateStatus.PARTIAL

    promotable = bool(
        company_id
        and trusted
        and aggregate_status in (AggregateStatus.READY, AggregateStatus.PARTIAL)
        and "entity_needs_review" not in partial_reasons
        and not blocking_reasons
    )
    known_providers = {provider for s in deduped for provider in s.source_providers}
    source_provider_count = max(
        len(known_providers),
        max((s.source_provider_count for s in deduped), default=0),
    )
    input_fingerprint = _aggregate_fingerprint(
        importer_identity=canonical_identity,
        company_resolved=company_id is not None,
        as_of_date=reference_date,
        window_days=window_days,
        previous_window_days=previous_window_days,
        rule_version=rule_version,
        shipments=deduped,
    )
    quality_summary = {
        "VERIFIED": sum(1 for s in included if s.quality_status.upper() == "VERIFIED"),
        "USABLE": sum(1 for s in included if s.quality_status.upper() == "USABLE"),
        "REVIEW": len(review_shipments),
        "REJECTED": len(rejected_shipments),
    }
    metrics: dict[str, Any] = {
        "shipment_count_90d": count_90,
        "shipment_count_365d": count_365,
        "shipment_count_730d": count_730,
        "shipment_count_previous_365d": count_previous,
        "active_month_count": len(months),
        "unique_supplier_count": len(suppliers),
        "unique_origin_country_count": len(origins),
        "unique_destination_port_count": len(ports),
        "unique_carrier_count": len(carriers),
        "known_origin_shipment_count": len(known_origins),
        "china_origin_shipment_count": china_count,
        "china_ratio": china_count / len(known_origins) if known_origins else None,
        "unknown_origin_shipment_count": len(trusted) - len(known_origins),
        "total_container_count": total_containers,
    }
    reasons = tuple(dict.fromkeys(blocking_reasons + partial_reasons))
    created_at = datetime.now(UTC)
    return ImporterEvidenceAggregate(
        company_id=company_id,
        importer_identity=canonical_identity,
        aggregate_version=AGGREGATE_VERSION,
        rule_version=rule_version,
        status=aggregate_status,
        promotable=promotable,
        input_fingerprint=input_fingerprint,
        as_of_date=reference_date,
        window_days=window_days,
        previous_window_days=previous_window_days,
        metrics_json=metrics,
        quality_summary_json=quality_summary,
        blocking_reasons=tuple(dict.fromkeys(blocking_reasons)),
        source_provider_count=source_provider_count,
        trusted_shipment_count=len(trusted),
        verified_shipment_count=quality_summary["VERIFIED"],
        usable_shipment_count=quality_summary["USABLE"],
        review_shipment_count=len(review_shipments),
        rejected_shipment_count=len(rejected_shipments),
        undated_shipment_count=undated_count,
        skipped_shipment_count=len(deduped) - len(included),
        active_month_count=len(months),
        unique_supplier_count=len(suppliers),
        unknown_supplier_count=sum(1 for s in trusted if not s.supplier.strip()),
        unique_origin_country_count=len(origins),
        unique_destination_port_count=len(ports),
        unique_carrier_count=len(carriers),
        earliest_arrival_date=dates[0] if dates else None,
        latest_arrival_date=dates[-1] if dates else None,
        known_origin_shipment_count=len(known_origins),
        china_origin_shipment_count=china_count,
        unknown_origin_shipment_count=len(trusted) - len(known_origins),
        total_container_count=total_containers,
        known_weight_kg=known_weight,
        shipment_count_90d=count_90,
        shipment_count_365d=count_365,
        shipment_count_730d=count_730,
        shipment_count_previous_365d=count_previous,
        median_days_between_shipments=median_days,
        trend_candidate=trend,
        status_reasons=reasons,
        inclusions=tuple(sorted(inclusions, key=lambda row: row.shipment_fingerprint)),
        created_at=created_at,
    )


def _deduplicate_shipments(
    shipments: Sequence[AggregateShipmentInput],
) -> list[AggregateShipmentInput]:
    grouped: dict[str, AggregateShipmentInput] = {}
    quality_rank = {"VERIFIED": 3, "USABLE": 2, "REVIEW": 1, "REJECTED": 0}
    for shipment in shipments:
        key = shipment.shipment_fingerprint or _fallback_business_fingerprint(shipment)
        current = grouped.get(key)
        if current is None:
            grouped[key] = shipment
            continue
        current_rank = quality_rank.get(current.quality_status.upper(), -1)
        candidate_rank = quality_rank.get(shipment.quality_status.upper(), -1)
        selected = (
            shipment
            if (candidate_rank, shipment.quality_fingerprint)
            > (
                current_rank,
                current.quality_fingerprint,
            )
            else current
        )
        grouped[key] = AggregateShipmentInput(
            **{
                **selected.__dict__,
                "source_provider_count": max(
                    len(set(current.source_providers) | set(shipment.source_providers)),
                    current.source_provider_count,
                    shipment.source_provider_count,
                ),
                "source_providers": tuple(
                    sorted(set(current.source_providers) | set(shipment.source_providers))
                ),
                "containers": tuple(sorted(set(current.containers) | set(shipment.containers))),
            }
        )
    return [grouped[key] for key in sorted(grouped)]


def _aggregate_fingerprint(
    *,
    importer_identity: str,
    company_resolved: bool,
    as_of_date: date,
    window_days: int,
    previous_window_days: int,
    rule_version: str,
    shipments: Sequence[AggregateShipmentInput],
) -> str:
    shipment_inputs = sorted(
        (
            {
                "shipment_fingerprint": s.shipment_fingerprint or _fallback_business_fingerprint(s),
                "quality_fingerprint": s.quality_fingerprint or "__MISSING__",
                "quality_hard_blockers": sorted(s.quality_hard_blockers),
                "dedupe_status": s.dedupe_status.lower().strip() or "__MISSING__",
                "entity_match_status": s.entity_match_status.lower().strip() or "__UNRESOLVED__",
            }
            for s in shipments
        ),
        key=lambda item: (item["shipment_fingerprint"], item["quality_fingerprint"]),
    )
    return stable_fingerprint(
        {
            "aggregate_version": AGGREGATE_VERSION,
            "rule_version": rule_version,
            "importer_identity": importer_identity or "__UNRESOLVED__",
            "company_resolved": company_resolved,
            "as_of_date": as_of_date.isoformat(),
            "window": {
                "current_days": window_days,
                "previous_days": previous_window_days,
            },
            "shipments": shipment_inputs,
        }
    )


def _fallback_business_fingerprint(shipment: AggregateShipmentInput) -> str:
    return stable_fingerprint(
        {
            "arrival_date": _business_date(shipment.arrival_date),
            "importer_identity": normalize_importer_identity(shipment.importer_identity),
            "origin": shipment.origin.upper().strip() or "__NULL__",
            "supplier": normalize_importer_identity(shipment.supplier) or "__NULL__",
            "carrier": shipment.carrier.upper().strip() or "__NULL__",
            "port": shipment.port.upper().strip() or "__NULL__",
            "containers": sorted({_normalize_container(c) for c in shipment.containers}),
        }
    )


def _inclusion(
    shipment: AggregateShipmentInput,
    status: InclusionStatus,
    reason: str,
) -> ShipmentInclusion:
    return ShipmentInclusion(
        normalized_shipment_id=shipment.normalized_shipment_id,
        quality_assessment_id=shipment.quality_assessment_id,
        shipment_fingerprint=shipment.shipment_fingerprint
        or _fallback_business_fingerprint(shipment),
        inclusion_status=status,
        inclusion_reason=reason,
        source_provider_count=shipment.source_provider_count,
    )


def _start_for_window(reference_date: date, days: int) -> date:
    """Inclusive window: both reference date and start date count."""
    return reference_date - timedelta(days=days - 1)


def _window_count(
    dated: Sequence[tuple[AggregateShipmentInput, date]], start: date, end: date
) -> int:
    return sum(1 for _, arrival in dated if start <= arrival <= end)


def _business_date(value: date | datetime | None) -> date | None:
    if isinstance(value, datetime):
        # Arrival is a customs business date. Preserve its recorded calendar
        # day instead of shifting it across a boundary through timezone conversion.
        return value.date()
    return value


def _median_gap(dates: Sequence[date]) -> float | None:
    if len(dates) < 2:
        return None
    gaps = sorted((dates[index + 1] - dates[index]).days for index in range(len(dates) - 1))
    midpoint = len(gaps) // 2
    if len(gaps) % 2:
        return float(gaps[midpoint])
    return (gaps[midpoint - 1] + gaps[midpoint]) / 2.0


def _trend(current: int, previous: int) -> str:
    if current < 2 or previous < 2:
        return "insufficient_data"
    if current > previous * 1.1:
        return "increasing"
    if current < previous * 0.9:
        return "decreasing"
    return "stable"


def normalize_importer_identity(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return re.sub(r"\s+", " ", normalized)


def _normalize_container(value: str) -> str:
    return re.sub(r"[-\s]+", "", value).upper()


def _uuid_or_none(value: object) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


def _float_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def serialize_aggregate(aggregate: ImporterEvidenceAggregate) -> str:
    """Compact deterministic representation useful in audit diagnostics."""
    return json.dumps(aggregate.metrics_json, sort_keys=True, separators=(",", ":"))
