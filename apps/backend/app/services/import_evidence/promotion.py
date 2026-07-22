"""Deterministic Stage 4A.4.3 promotion eligibility policy."""

from collections.abc import Sequence
from uuid import UUID

from app.domain.import_evidence.models import (
    AggregateStatus,
    ImporterEvidenceAggregate,
    InclusionStatus,
    PromotionStatus,
    QualityAssessment,
    QualityStatus,
    ShipmentInclusion,
    SignalPromotionCandidate,
    stable_fingerprint,
)

PROMOTION_VERSION = "import-evidence-signal-promotion-v1"
PROMOTION_POLICY_VERSION = "import-evidence-signal-rules-v1"
SUPPORTED_SIGNAL_KINDS = (
    "import_activity",
    "china_dependency",
    "logistics_complexity",
)


class PromotionEligibilityPolicy:
    """One deterministic policy owns aggregate, quality and dimension gates."""

    def preview(
        self,
        aggregate: ImporterEvidenceAggregate,
        quality_assessments: Sequence[QualityAssessment],
    ) -> tuple[SignalPromotionCandidate, ...]:
        qualities = {assessment.id: assessment for assessment in quality_assessments}
        contributing = tuple(
            inclusion
            for inclusion in aggregate.inclusions
            if inclusion.inclusion_status in (InclusionStatus.TRUSTED, InclusionStatus.UNDATED)
        )
        quality_rows = tuple(
            qualities[inclusion.quality_assessment_id]
            for inclusion in contributing
            if inclusion.quality_assessment_id in qualities
        )
        global_reasons = self._global_reasons(aggregate, contributing, quality_rows)
        quality_status, quality_score = self._quality_summary(quality_rows)
        evidence = self._evidence_snapshot(aggregate, contributing, qualities)
        source = {
            "source": "import_evidence",
            "source_provider_count": aggregate.source_provider_count,
            "trusted_shipment_count": aggregate.trusted_shipment_count,
            "aggregate_id": str(aggregate.id),
            "as_of_date": aggregate.as_of_date.isoformat(),
        }

        builders = {
            "import_activity": self._import_activity,
            "china_dependency": self._china_dependency,
            "logistics_complexity": self._logistics_complexity,
        }
        candidates: list[SignalPromotionCandidate] = []
        for kind in SUPPORTED_SIGNAL_KINDS:
            normalized, detail, reasons = builders[kind](aggregate)
            quality_label = quality_status.value if quality_status else "UNKNOWN"
            detail = (
                f"{detail} Aggregate {aggregate.id}；Quality {quality_label}"
                f"（{quality_score if quality_score is not None else 'unknown'}）。"
            )
            all_reasons = tuple(dict.fromkeys((*global_reasons, *reasons)))
            if global_reasons:
                status = (
                    PromotionStatus.SKIPPED
                    if aggregate.status is AggregateStatus.INSUFFICIENT_DATA
                    else PromotionStatus.BLOCKED
                )
            elif reasons:
                status = PromotionStatus.SKIPPED
            else:
                status = PromotionStatus.CANDIDATE
            fingerprint = stable_fingerprint(
                {
                    "promotion_version": PROMOTION_VERSION,
                    "policy_version": PROMOTION_POLICY_VERSION,
                    "aggregate_fingerprint": aggregate.input_fingerprint or "__MISSING__",
                    "signal_kind": kind,
                    "normalized_value": normalized,
                    "quality_fingerprints": sorted(
                        assessment.input_fingerprint for assessment in quality_rows
                    ),
                    "decision_reasons": sorted(all_reasons),
                }
            )
            candidates.append(
                SignalPromotionCandidate(
                    aggregate_id=aggregate.id,
                    company_id=aggregate.company_id,
                    signal_kind=kind,
                    signal_detail=detail,
                    normalized_value_json=normalized,
                    source_summary_json=source,
                    evidence_snapshot_json=evidence,
                    quality_status=quality_status,
                    quality_score=quality_score,
                    promotion_version=PROMOTION_VERSION,
                    input_fingerprint=fingerprint,
                    status=status,
                    quality_assessment_ids=tuple(
                        sorted((assessment.id for assessment in quality_rows), key=str)
                    ),
                    rejection_reasons=all_reasons,
                )
            )
        return tuple(candidates)

    @staticmethod
    def _global_reasons(
        aggregate: ImporterEvidenceAggregate,
        contributing: Sequence[ShipmentInclusion],
        quality_rows: Sequence[QualityAssessment],
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if not aggregate.is_current:
            reasons.append("aggregate_not_current")
        if aggregate.company_id is None:
            reasons.append("company_unresolved")
        if not aggregate.promotable:
            reasons.append("aggregate_not_promotable")
        if not aggregate.input_fingerprint:
            reasons.append("aggregate_fingerprint_missing")
        if aggregate.blocking_reasons:
            reasons.extend(f"aggregate_blocker:{reason}" for reason in aggregate.blocking_reasons)
        if aggregate.status is AggregateStatus.BLOCKED:
            reasons.append("aggregate_blocked")
        elif aggregate.status is AggregateStatus.INSUFFICIENT_DATA:
            reasons.append("aggregate_insufficient_data")
        if not contributing:
            reasons.append("no_trusted_inclusions")
        if len(quality_rows) != len(contributing):
            reasons.append("quality_assessment_untraceable")
        for quality in quality_rows:
            if not quality.is_current:
                reasons.append("quality_assessment_not_current")
            if quality.quality_status is QualityStatus.REVIEW:
                reasons.append("quality_requires_review")
            elif quality.quality_status is QualityStatus.REJECTED:
                reasons.append("quality_rejected")
            if not quality.input_fingerprint:
                reasons.append("quality_fingerprint_missing")
        return tuple(dict.fromkeys(reasons))

    @staticmethod
    def _quality_summary(
        quality_rows: Sequence[QualityAssessment],
    ) -> tuple[QualityStatus | None, float | None]:
        if not quality_rows:
            return None, None
        statuses = {assessment.quality_status for assessment in quality_rows}
        if QualityStatus.REJECTED in statuses:
            status = QualityStatus.REJECTED
        elif QualityStatus.REVIEW in statuses:
            status = QualityStatus.REVIEW
        elif QualityStatus.USABLE in statuses:
            status = QualityStatus.USABLE
        else:
            status = QualityStatus.VERIFIED
        return status, min(assessment.total_score for assessment in quality_rows)

    @staticmethod
    def _evidence_snapshot(
        aggregate: ImporterEvidenceAggregate,
        contributing: Sequence[ShipmentInclusion],
        qualities: dict[UUID, QualityAssessment],
    ) -> dict[str, object]:
        rows: list[dict[str, object]] = []
        for inclusion in aggregate.inclusions:
            if inclusion not in contributing:
                continue
            quality = (
                qualities.get(inclusion.quality_assessment_id)
                if inclusion.quality_assessment_id
                else None
            )
            rows.append(
                {
                    "normalized_shipment_id": str(inclusion.normalized_shipment_id),
                    "shipment_fingerprint": inclusion.shipment_fingerprint,
                    "inclusion_status": inclusion.inclusion_status.value,
                    "quality_assessment_id": (
                        str(inclusion.quality_assessment_id)
                        if inclusion.quality_assessment_id
                        else None
                    ),
                    "quality_fingerprint": quality.input_fingerprint if quality else None,
                    "quality_status": quality.quality_status.value if quality else None,
                    "quality_score": quality.total_score if quality else None,
                }
            )
        return {
            "aggregate_id": str(aggregate.id),
            "aggregate_fingerprint": aggregate.input_fingerprint,
            "shipments": sorted(rows, key=lambda row: str(row["shipment_fingerprint"])),
        }

    @staticmethod
    def _import_activity(
        aggregate: ImporterEvidenceAggregate,
    ) -> tuple[dict[str, object], str, tuple[str, ...]]:
        normalized: dict[str, object] = {
            "shipment_count_90d": aggregate.shipment_count_90d,
            "shipment_count_365d": aggregate.shipment_count_365d,
            "shipment_count_730d": aggregate.shipment_count_730d,
            "shipment_count_previous_365d": aggregate.shipment_count_previous_365d,
            "trend": aggregate.trend_candidate,
            "window_days": aggregate.window_days,
            "as_of_date": aggregate.as_of_date.isoformat(),
            "trusted_shipment_count": aggregate.trusted_shipment_count,
            "aggregate_id": str(aggregate.id),
        }
        eligible = aggregate.shipment_count_365d >= 2 or (
            aggregate.verified_shipment_count >= 1 and aggregate.shipment_count_90d >= 1
        )
        detail = (
            f"截至 {aggregate.as_of_date.isoformat()}，过去90天记录"
            f" {aggregate.shipment_count_90d} 票、365天 {aggregate.shipment_count_365d} 票、"
            f"730天 {aggregate.shipment_count_730d} 票可追踪进口；前一365天"
            f" {aggregate.shipment_count_previous_365d} 票，趋势为 {aggregate.trend_candidate}。"
        )
        return normalized, detail, () if eligible else ("import_activity_sample_insufficient",)

    @staticmethod
    def _china_dependency(
        aggregate: ImporterEvidenceAggregate,
    ) -> tuple[dict[str, object], str, tuple[str, ...]]:
        known = aggregate.known_origin_shipment_count
        china = aggregate.china_origin_shipment_count
        ratio = china / known if known else None
        coverage = (
            known / aggregate.trusted_shipment_count if aggregate.trusted_shipment_count else 0.0
        )
        normalized: dict[str, object] = {
            "china_origin_shipment_count": china,
            "known_origin_shipment_count": known,
            "unknown_origin_shipment_count": aggregate.unknown_origin_shipment_count,
            "china_ratio": ratio,
            "origin_coverage": coverage,
            "window_days": aggregate.window_days,
            "as_of_date": aggregate.as_of_date.isoformat(),
            "aggregate_id": str(aggregate.id),
        }
        reasons: list[str] = []
        if known == 0:
            reasons.append("known_origin_missing")
        elif known < 3:
            reasons.append("known_origin_sample_insufficient")
        if coverage < 0.5:
            reasons.append("origin_coverage_below_threshold")
        if ratio is None or ratio < 0.5:
            reasons.append("china_ratio_below_threshold")
        ratio_text = "未知" if ratio is None else f"{ratio:.0%}"
        detail = (
            f"截至 {aggregate.as_of_date.isoformat()}，已知来源的 {known} 票进口中，"
            f"{china} 票来源于中国，中国来源占比 {ratio_text}；未知来源未计入分母。"
        )
        return normalized, detail, tuple(reasons)

    @staticmethod
    def _logistics_complexity(
        aggregate: ImporterEvidenceAggregate,
    ) -> tuple[dict[str, object], str, tuple[str, ...]]:
        metrics = {
            "unique_supplier_count": aggregate.unique_supplier_count,
            "unique_carrier_count": aggregate.unique_carrier_count,
            "unique_destination_port_count": aggregate.unique_destination_port_count,
            "trusted_shipment_count": aggregate.trusted_shipment_count,
            "total_container_count": aggregate.total_container_count,
            "active_month_count": aggregate.active_month_count,
        }
        conditions = {
            "suppliers": aggregate.unique_supplier_count >= 3,
            "carriers": aggregate.unique_carrier_count >= 2,
            "ports": aggregate.unique_destination_port_count >= 2,
            "shipments": aggregate.trusted_shipment_count >= 3,
            "containers": aggregate.total_container_count >= 3,
            "months": aggregate.active_month_count >= 3,
        }
        categories = set()
        if any(conditions[key] for key in ("suppliers", "carriers", "ports")):
            categories.add("network")
        if any(conditions[key] for key in ("shipments", "months")):
            categories.add("cadence")
        if conditions["containers"]:
            categories.add("equipment")
        met = [key for key, value in conditions.items() if value]
        normalized: dict[str, object] = {
            **metrics,
            "conditions_met": met,
            "evidence_categories": sorted(categories),
            "window_days": aggregate.window_days,
            "as_of_date": aggregate.as_of_date.isoformat(),
            "aggregate_id": str(aggregate.id),
        }
        detail = (
            f"截至 {aggregate.as_of_date.isoformat()}，可追踪进口涉及"
            f" {aggregate.unique_supplier_count} 家供应商、"
            f"{aggregate.unique_carrier_count} 个承运人、"
            f"{aggregate.unique_destination_port_count} 个到港节点、"
            f"{aggregate.total_container_count} 个去重箱号和"
            f" {aggregate.trusted_shipment_count} 票 Shipment。"
        )
        reasons = (
            ()
            if len(met) >= 3 and len(categories) >= 2
            else ("logistics_complexity_evidence_insufficient",)
        )
        return normalized, detail, reasons
