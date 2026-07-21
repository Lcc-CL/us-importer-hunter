"""Importer evidence aggregate: shipment metrics for one resolved company."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

AGGREGATE_VERSION = "importer-evidence-aggregate-v1"


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


@dataclass(frozen=True)
class ShipmentInclusion:
    shipment_id: UUID
    quality_assessment_id: UUID | None = None
    inclusion_status: InclusionStatus = InclusionStatus.SKIPPED
    inclusion_reason: str = ""


@dataclass(frozen=True)
class ImporterEvidenceAggregate:
    id: UUID = field(default_factory=uuid4)
    company_id: UUID | None = None
    aggregate_version: str = AGGREGATE_VERSION
    window_days: int = 365
    as_of_date: date = field(default_factory=lambda: date.today())
    input_fingerprint: str = ""
    is_current: bool = True

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

    status: AggregateStatus = AggregateStatus.INSUFFICIENT_DATA
    metrics_json: dict[str, Any] = field(default_factory=dict)
    status_reasons: tuple[str, ...] = ()

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def compute_aggregate(
    *,
    company_id: UUID | None,
    shipments: list[dict[str, Any]],
    window_days: int = 365,
    as_of_date: date | None = None,
) -> ImporterEvidenceAggregate:
    ref_date = as_of_date or date.today()
    start_date = _start_for_window(ref_date, window_days)
    prev_start = _start_for_window(ref_date, window_days * 2)
    prev_end = start_date

    trusted: list[dict[str, Any]] = []
    review_s: list[dict[str, Any]] = []
    rejected_s: list[dict[str, Any]] = []
    undated: list[dict[str, Any]] = []

    for s in shipments:
        q = s.get("quality", "")
        if q in ("VERIFIED", "USABLE"):
            trusted.append(s)
        elif q == "REVIEW":
            review_s.append(s)
        elif q == "REJECTED":
            rejected_s.append(s)
        else:
            rejected_s.append(s)
        if not s.get("arrival_date"):
            undated.append(s)

    in_window = [s for s in trusted if s.get("arrival_date") and s["arrival_date"] >= start_date and s["arrival_date"] <= ref_date]
    in_365 = [s for s in trusted if s.get("arrival_date") and s["arrival_date"] >= start_date and s["arrival_date"] <= ref_date]
    in_730 = [s for s in trusted if s.get("arrival_date") and s["arrival_date"] >= _start_for_window(ref_date, 730) and s["arrival_date"] <= ref_date]
    in_90 = [s for s in trusted if s.get("arrival_date") and s["arrival_date"] >= _start_for_window(ref_date, 90) and s["arrival_date"] <= ref_date]
    prev_365 = [s for s in trusted if s.get("arrival_date") and s["arrival_date"] >= prev_start and s["arrival_date"] < start_date]

    suppliers = set()
    unknown_supp = 0
    for s in trusted:
        sup = s.get("supplier", "").strip()
        if sup:
            suppliers.add(sup.lower())
        else:
            unknown_supp += 1

    origins = set()
    china = 0
    known_origin = 0
    unknown_origin = 0
    for s in trusted:
        o = s.get("origin", "").upper().strip()
        if o:
            known_origin += 1
            origins.add(o)
            if o == "CN":
                china += 1
        else:
            unknown_origin += 1

    ports = set()
    carriers = set()
    for s in trusted:
        p = s.get("port", "").strip().upper()
        if p:
            ports.add(p)
        c = s.get("carrier", "").strip().upper()
        if c:
            carriers.add(c)

    containers = 0
    seen_containers = set()
    for s in trusted:
        for cn in s.get("containers", []):
            if cn not in seen_containers:
                containers += 1
                seen_containers.add(cn)

    weight = None
    for s in trusted:
        w = s.get("weight_kg")
        if w is not None and weight is None:
            weight = w

    dates = sorted([s["arrival_date"] for s in trusted if s.get("arrival_date")])
    months = set((d.year, d.month) for d in dates)
    median_days = None
    if len(dates) >= 2:
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        gaps.sort()
        median_days = float(gaps[len(gaps) // 2])

    if len(prev_365) >= 2 and len(in_365) >= 2:
        if len(in_365) > len(prev_365) * 1.1:
            trend = "increasing"
        elif len(in_365) < len(prev_365) * 0.9:
            trend = "decreasing"
        else:
            trend = "stable"
    else:
        trend = "insufficient_data"

    status = AggregateStatus.INSUFFICIENT_DATA
    reasons = []
    if len(trusted) >= 1 and company_id:
        status = AggregateStatus.READY
    elif len(trusted) >= 1:
        status = AggregateStatus.PARTIAL
        reasons.append("company_not_resolved")
    else:
        reasons.append("no_trusted_shipments")

    return ImporterEvidenceAggregate(
        company_id=company_id,
        window_days=window_days,
        as_of_date=ref_date,
        trusted_shipment_count=len(trusted),
        verified_shipment_count=sum(1 for s in trusted if s.get("quality") == "VERIFIED"),
        usable_shipment_count=sum(1 for s in trusted if s.get("quality") == "USABLE"),
        review_shipment_count=len(review_s),
        rejected_shipment_count=len(rejected_s),
        undated_shipment_count=len(undated),
        skipped_shipment_count=0,
        active_month_count=len(months),
        unique_supplier_count=len(suppliers),
        unknown_supplier_count=unknown_supp,
        unique_origin_country_count=len(origins),
        unique_destination_port_count=len(ports),
        unique_carrier_count=len(carriers),
        earliest_arrival_date=dates[0] if dates else None,
        latest_arrival_date=dates[-1] if dates else None,
        known_origin_shipment_count=known_origin,
        china_origin_shipment_count=china,
        unknown_origin_shipment_count=unknown_origin,
        total_container_count=containers,
        known_weight_kg=weight,
        shipment_count_90d=len(in_90),
        shipment_count_365d=len(in_365),
        shipment_count_730d=len(in_730),
        shipment_count_previous_365d=len(prev_365),
        median_days_between_shipments=median_days,
        trend_candidate=trend,
        status=status,
        status_reasons=tuple(reasons),
    )


def _start_for_window(ref: date, days: int) -> date:
    from datetime import timedelta
    return ref - timedelta(days=days)
