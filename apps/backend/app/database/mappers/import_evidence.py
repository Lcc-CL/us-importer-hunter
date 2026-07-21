"""Import-evidence quality and aggregate domain ↔ persistence mapping."""

from datetime import date
from typing import Any
from uuid import UUID

from app.database.models.import_evidence import (
    ImporterEvidenceAggregateModel,
    ImporterEvidenceAggregateShipmentModel,
    ImportEvidenceQualityAssessmentModel,
)
from app.domain.import_evidence.models import (
    AggregateStatus,
    ImporterEvidenceAggregate,
    InclusionStatus,
    QualityAssessment,
    QualityStatus,
    ShipmentInclusion,
)


class ImportEvidenceQualityMapper:
    @staticmethod
    def to_model(assessment: QualityAssessment) -> ImportEvidenceQualityAssessmentModel:
        if assessment.normalized_shipment_id is None:
            raise ValueError("quality assessment requires normalized_shipment_id")
        if not assessment.input_fingerprint:
            raise ValueError("quality assessment requires input_fingerprint")
        return ImportEvidenceQualityAssessmentModel(
            id=assessment.id,
            normalized_shipment_id=assessment.normalized_shipment_id,
            assessment_version=assessment.assessment_version,
            status=assessment.quality_status.value,
            total_score=assessment.total_score,
            source_reliability_score=assessment.source_reliability_score,
            entity_resolution_score=assessment.entity_resolution_score,
            identity_completeness_score=assessment.identity_completeness_score,
            cross_source_consistency_score=assessment.cross_source_consistency_score,
            freshness_score=assessment.freshness_score,
            penalties_json=list(assessment.penalties),
            hard_blockers_json=list(assessment.hard_blockers),
            reasons_json=list(assessment.reasons),
            input_fingerprint=assessment.input_fingerprint,
            is_current=assessment.is_current,
            assessed_at=assessment.assessed_at,
            superseded_at=assessment.superseded_at,
            created_at=assessment.created_at,
        )

    @staticmethod
    def to_domain(model: ImportEvidenceQualityAssessmentModel) -> QualityAssessment:
        return QualityAssessment(
            id=model.id,
            normalized_shipment_id=model.normalized_shipment_id,
            assessment_version=model.assessment_version,
            total_score=model.total_score,
            quality_status=QualityStatus(model.status),
            source_reliability_score=model.source_reliability_score,
            entity_resolution_score=model.entity_resolution_score,
            identity_completeness_score=model.identity_completeness_score,
            cross_source_consistency_score=model.cross_source_consistency_score,
            freshness_score=model.freshness_score,
            penalties=tuple(model.penalties_json or ()),
            hard_blockers=tuple(model.hard_blockers_json or ()),
            reasons=tuple(model.reasons_json or ()),
            input_fingerprint=model.input_fingerprint,
            is_current=model.is_current,
            assessed_at=model.assessed_at,
            superseded_at=model.superseded_at,
            created_at=model.created_at,
        )


class ImporterEvidenceAggregateMapper:
    @staticmethod
    def to_model(aggregate: ImporterEvidenceAggregate) -> ImporterEvidenceAggregateModel:
        if not aggregate.importer_identity:
            raise ValueError("aggregate requires importer_identity")
        if not aggregate.input_fingerprint:
            raise ValueError("aggregate requires input_fingerprint")
        metrics = _metrics_payload(aggregate)
        return ImporterEvidenceAggregateModel(
            id=aggregate.id,
            company_id=aggregate.company_id,
            importer_identity=aggregate.importer_identity,
            aggregate_version=aggregate.aggregate_version,
            rule_version=aggregate.rule_version,
            aggregate_status=aggregate.status.value,
            promotable=aggregate.promotable,
            input_fingerprint=aggregate.input_fingerprint,
            is_current=aggregate.is_current,
            as_of_date=aggregate.as_of_date,
            window_days=aggregate.window_days,
            previous_window_days=aggregate.previous_window_days,
            metrics_json=metrics,
            quality_summary_json=aggregate.quality_summary_json,
            blocking_reasons_json=list(aggregate.blocking_reasons),
            status_reasons_json=list(aggregate.status_reasons),
            source_provider_count=aggregate.source_provider_count,
            trusted_shipment_count=aggregate.trusted_shipment_count,
            created_at=aggregate.created_at,
            superseded_at=aggregate.superseded_at,
        )

    @staticmethod
    def inclusion_to_model(
        aggregate_id: UUID,
        inclusion: ShipmentInclusion,
    ) -> ImporterEvidenceAggregateShipmentModel:
        return ImporterEvidenceAggregateShipmentModel(
            aggregate_id=aggregate_id,
            normalized_shipment_id=inclusion.normalized_shipment_id,
            quality_assessment_id=inclusion.quality_assessment_id,
            shipment_fingerprint=inclusion.shipment_fingerprint,
            inclusion_status=inclusion.inclusion_status.value,
            inclusion_reason=inclusion.inclusion_reason,
            source_provider_count=inclusion.source_provider_count,
            created_at=inclusion.created_at,
        )

    @staticmethod
    def inclusion_to_domain(
        row: ImporterEvidenceAggregateShipmentModel,
    ) -> ShipmentInclusion:
        return ShipmentInclusion(
            normalized_shipment_id=row.normalized_shipment_id,
            quality_assessment_id=row.quality_assessment_id,
            shipment_fingerprint=row.shipment_fingerprint,
            inclusion_status=InclusionStatus(row.inclusion_status),
            inclusion_reason=row.inclusion_reason,
            source_provider_count=row.source_provider_count,
            created_at=row.created_at,
        )

    @staticmethod
    def to_domain(
        model: ImporterEvidenceAggregateModel,
        inclusion_models: list[ImporterEvidenceAggregateShipmentModel],
    ) -> ImporterEvidenceAggregate:
        metrics = model.metrics_json or {}
        inclusions = tuple(
            ImporterEvidenceAggregateMapper.inclusion_to_domain(row) for row in inclusion_models
        )
        return ImporterEvidenceAggregate(
            id=model.id,
            company_id=model.company_id,
            importer_identity=model.importer_identity,
            aggregate_version=model.aggregate_version,
            rule_version=model.rule_version,
            status=AggregateStatus(model.aggregate_status),
            promotable=model.promotable,
            input_fingerprint=model.input_fingerprint,
            is_current=model.is_current,
            as_of_date=model.as_of_date,
            window_days=model.window_days,
            previous_window_days=model.previous_window_days,
            metrics_json=dict(metrics),
            quality_summary_json=dict(model.quality_summary_json or {}),
            blocking_reasons=tuple(model.blocking_reasons_json or ()),
            source_provider_count=model.source_provider_count,
            trusted_shipment_count=model.trusted_shipment_count,
            verified_shipment_count=_int(metrics, "verified_shipment_count"),
            usable_shipment_count=_int(metrics, "usable_shipment_count"),
            review_shipment_count=_int(metrics, "review_shipment_count"),
            rejected_shipment_count=_int(metrics, "rejected_shipment_count"),
            undated_shipment_count=_int(metrics, "undated_shipment_count"),
            skipped_shipment_count=_int(metrics, "skipped_shipment_count"),
            active_month_count=_int(metrics, "active_month_count"),
            unique_supplier_count=_int(metrics, "unique_supplier_count"),
            unknown_supplier_count=_int(metrics, "unknown_supplier_count"),
            unique_origin_country_count=_int(metrics, "unique_origin_country_count"),
            unique_destination_port_count=_int(metrics, "unique_destination_port_count"),
            unique_carrier_count=_int(metrics, "unique_carrier_count"),
            earliest_arrival_date=_date_or_none(metrics.get("earliest_arrival_date")),
            latest_arrival_date=_date_or_none(metrics.get("latest_arrival_date")),
            known_origin_shipment_count=_int(metrics, "known_origin_shipment_count"),
            china_origin_shipment_count=_int(metrics, "china_origin_shipment_count"),
            unknown_origin_shipment_count=_int(metrics, "unknown_origin_shipment_count"),
            total_container_count=_int(metrics, "total_container_count"),
            known_weight_kg=_float_or_none(metrics.get("known_weight_kg")),
            shipment_count_90d=_int(metrics, "shipment_count_90d"),
            shipment_count_365d=_int(metrics, "shipment_count_365d"),
            shipment_count_730d=_int(metrics, "shipment_count_730d"),
            shipment_count_previous_365d=_int(metrics, "shipment_count_previous_365d"),
            median_days_between_shipments=_float_or_none(
                metrics.get("median_days_between_shipments")
            ),
            trend_candidate=str(metrics.get("trend_candidate") or "insufficient_data"),
            status_reasons=tuple(model.status_reasons_json or ()),
            inclusions=inclusions,
            created_at=model.created_at,
            superseded_at=model.superseded_at,
        )


def _metrics_payload(aggregate: ImporterEvidenceAggregate) -> dict[str, Any]:
    metrics = dict(aggregate.metrics_json)
    metrics.update(
        {
            "verified_shipment_count": aggregate.verified_shipment_count,
            "usable_shipment_count": aggregate.usable_shipment_count,
            "review_shipment_count": aggregate.review_shipment_count,
            "rejected_shipment_count": aggregate.rejected_shipment_count,
            "undated_shipment_count": aggregate.undated_shipment_count,
            "skipped_shipment_count": aggregate.skipped_shipment_count,
            "active_month_count": aggregate.active_month_count,
            "unique_supplier_count": aggregate.unique_supplier_count,
            "unknown_supplier_count": aggregate.unknown_supplier_count,
            "unique_origin_country_count": aggregate.unique_origin_country_count,
            "unique_destination_port_count": aggregate.unique_destination_port_count,
            "unique_carrier_count": aggregate.unique_carrier_count,
            "earliest_arrival_date": (
                aggregate.earliest_arrival_date.isoformat()
                if aggregate.earliest_arrival_date
                else None
            ),
            "latest_arrival_date": (
                aggregate.latest_arrival_date.isoformat() if aggregate.latest_arrival_date else None
            ),
            "known_origin_shipment_count": aggregate.known_origin_shipment_count,
            "china_origin_shipment_count": aggregate.china_origin_shipment_count,
            "unknown_origin_shipment_count": aggregate.unknown_origin_shipment_count,
            "total_container_count": aggregate.total_container_count,
            "known_weight_kg": aggregate.known_weight_kg,
            "shipment_count_90d": aggregate.shipment_count_90d,
            "shipment_count_365d": aggregate.shipment_count_365d,
            "shipment_count_730d": aggregate.shipment_count_730d,
            "shipment_count_previous_365d": aggregate.shipment_count_previous_365d,
            "median_days_between_shipments": aggregate.median_days_between_shipments,
            "trend_candidate": aggregate.trend_candidate,
        }
    )
    return metrics


def _int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    return int(value) if isinstance(value, (int, float)) else 0


def _float_or_none(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _date_or_none(value: object) -> date | None:
    if isinstance(value, str):
        return date.fromisoformat(value)
    return None
