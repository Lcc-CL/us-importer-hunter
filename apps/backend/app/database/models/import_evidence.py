"""Import evidence persistence: raw records, shipments, matches, signals, snapshots, conflicts."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ImportEvidenceJobModel(Base):
    __tablename__ = "import_evidence_jobs"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    provider_name: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    request_id: Mapped[UUID] = mapped_column()
    total_raw: Mapped[int] = mapped_column(Integer, default=0)
    total_normalized: Mapped[int] = mapped_column(Integer, default=0)
    total_deduped: Mapped[int] = mapped_column(Integer, default=0)
    total_matched: Mapped[int] = mapped_column(Integer, default=0)
    total_promoted: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','partial','failed','needs_review')",
            name="ck_evidence_job_status",
        ),
        Index("ix_evidence_jobs_company", "company_id"),
    )


class ImportEvidenceRawRecordModel(Base):
    __tablename__ = "import_evidence_raw_records"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_record_id",
            "raw_payload_hash",
            name="uq_raw_record_dedup",
        ),
        Index("ix_raw_records_job", "job_id"),
        Index("ix_raw_records_provider", "provider"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("import_evidence_jobs.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(50))
    provider_record_id: Mapped[str] = mapped_column(String(200))
    request_id: Mapped[UUID] = mapped_column()
    raw_payload_json: Mapped[str] = mapped_column(Text)
    raw_payload_hash: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    schema_version: Mapped[str] = mapped_column(String(10), default="v1")
    fixture: Mapped[bool] = mapped_column(default=False)
    synthetic: Mapped[bool] = mapped_column(default=False)


class NormalizedShipmentModel(Base):
    __tablename__ = "normalized_shipments"
    __table_args__ = (
        UniqueConstraint("shipment_fingerprint", name="uq_shipment_fingerprint"),
        Index("ix_shipments_importer", "normalized_importer"),
        Index("ix_shipments_arrival", "arrival_date"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("import_evidence_jobs.id", ondelete="CASCADE"))
    importer_name: Mapped[str] = mapped_column(String(300))
    importer_address: Mapped[str] = mapped_column(Text, default="")
    normalized_importer: Mapped[str] = mapped_column(String(300))
    shipper_name: Mapped[str] = mapped_column(String(300))
    shipper_country: Mapped[str] = mapped_column(String(2))
    country_of_origin: Mapped[str] = mapped_column(String(2))
    arrival_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    port_of_lading: Mapped[str] = mapped_column(String(100))
    port_of_discharge: Mapped[str] = mapped_column(String(100))
    master_bol: Mapped[str] = mapped_column(String(50))
    house_bol: Mapped[str] = mapped_column(String(50))
    carrier_scac: Mapped[str] = mapped_column(String(10))
    vessel: Mapped[str] = mapped_column(String(100))
    voyage: Mapped[str] = mapped_column(String(20))
    container_numbers_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    teu: Mapped[float | None] = mapped_column(Float)
    hs_codes_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    goods_description_raw: Mapped[str] = mapped_column(Text)
    goods_description_normalized: Mapped[str] = mapped_column(Text)
    value_amount: Mapped[float | None] = mapped_column(Float)
    value_type: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(50))
    provider_record_id: Mapped[str] = mapped_column(String(200))
    shipment_fingerprint: Mapped[str] = mapped_column(String(64))
    fingerprint_version: Mapped[str] = mapped_column(String(20), default="shipment-fp-v1")
    dedupe_status: Mapped[str] = mapped_column(String(30), default="ok")
    dedupe_method: Mapped[str] = mapped_column(String(20), default="fingerprint")
    dedupe_reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    container_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_weight: Mapped[float | None] = mapped_column(Float)
    raw_weight_unit: Mapped[str] = mapped_column(String(10), default="")
    normalized_weight: Mapped[float | None] = mapped_column(Float)
    normalized_weight_unit: Mapped[str] = mapped_column(String(10), default="kg")
    weight_scope: Mapped[str] = mapped_column(String(20), default="unknown")
    raw_quantity: Mapped[float | None] = mapped_column(Float)
    normalized_quantity: Mapped[float | None] = mapped_column(Float)
    parent_shipment_id: Mapped[UUID | None] = mapped_column()
    normalization_version: Mapped[str] = mapped_column(String(10), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_record_ids_json: Mapped[list[str]] = mapped_column(JSONB, default=list)


class ImportEvidenceQualityAssessmentModel(Base):
    __tablename__ = "import_evidence_quality_assessments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('VERIFIED','USABLE','REVIEW','REJECTED')",
            name="ck_import_quality_status",
        ),
        CheckConstraint("total_score BETWEEN 0 AND 100", name="ck_import_quality_total"),
        CheckConstraint(
            "source_reliability_score BETWEEN 0 AND 100 "
            "AND entity_resolution_score BETWEEN 0 AND 100 "
            "AND identity_completeness_score BETWEEN 0 AND 100 "
            "AND cross_source_consistency_score BETWEEN 0 AND 100 "
            "AND freshness_score BETWEEN 0 AND 100",
            name="ck_import_quality_dimensions",
        ),
        UniqueConstraint(
            "normalized_shipment_id",
            "input_fingerprint",
            name="uq_import_quality_shipment_fingerprint",
        ),
        Index(
            "uq_import_quality_current_shipment",
            "normalized_shipment_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    normalized_shipment_id: Mapped[UUID] = mapped_column(
        ForeignKey("normalized_shipments.id", ondelete="CASCADE")
    )
    assessment_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    total_score: Mapped[float] = mapped_column(Float)
    source_reliability_score: Mapped[float] = mapped_column(Float)
    entity_resolution_score: Mapped[float] = mapped_column(Float)
    identity_completeness_score: Mapped[float] = mapped_column(Float)
    cross_source_consistency_score: Mapped[float] = mapped_column(Float)
    freshness_score: Mapped[float] = mapped_column(Float)
    penalties_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    hard_blockers_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    reasons_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ImporterEvidenceAggregateModel(Base):
    __tablename__ = "importer_evidence_aggregates"
    __table_args__ = (
        CheckConstraint(
            "aggregate_status IN ('READY','PARTIAL','INSUFFICIENT_DATA','BLOCKED')",
            name="ck_importer_aggregate_status",
        ),
        CheckConstraint("window_days > 0", name="ck_importer_aggregate_window"),
        CheckConstraint(
            "previous_window_days > 0",
            name="ck_importer_aggregate_previous_window",
        ),
        CheckConstraint(
            "NOT promotable OR company_id IS NOT NULL",
            name="ck_importer_aggregate_promotable_company",
        ),
        UniqueConstraint(
            "importer_identity",
            "window_days",
            "as_of_date",
            "input_fingerprint",
            name="uq_importer_aggregate_input",
        ),
        Index(
            "uq_importer_aggregate_current",
            "importer_identity",
            "window_days",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index("ix_importer_aggregates_company", "company_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    importer_identity: Mapped[str] = mapped_column(String(300))
    aggregate_version: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[str] = mapped_column(String(64))
    aggregate_status: Mapped[str] = mapped_column(String(30))
    promotable: Mapped[bool] = mapped_column(Boolean, default=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    as_of_date: Mapped[date] = mapped_column(Date)
    window_days: Mapped[int] = mapped_column(Integer)
    previous_window_days: Mapped[int] = mapped_column(Integer)
    metrics_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    quality_summary_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    blocking_reasons_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    status_reasons_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    source_provider_count: Mapped[int] = mapped_column(Integer, default=0)
    trusted_shipment_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImporterEvidenceAggregateShipmentModel(Base):
    __tablename__ = "importer_evidence_aggregate_shipments"
    __table_args__ = (
        CheckConstraint(
            "inclusion_status IN ('trusted','review','rejected','undated','skipped')",
            name="ck_importer_aggregate_inclusion_status",
        ),
        CheckConstraint(
            "source_provider_count >= 0",
            name="ck_importer_aggregate_source_count",
        ),
        UniqueConstraint(
            "aggregate_id",
            "shipment_fingerprint",
            name="uq_importer_aggregate_business_shipment",
        ),
    )

    aggregate_id: Mapped[UUID] = mapped_column(
        ForeignKey("importer_evidence_aggregates.id", ondelete="CASCADE"),
        primary_key=True,
    )
    normalized_shipment_id: Mapped[UUID] = mapped_column(
        ForeignKey("normalized_shipments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    quality_assessment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("import_evidence_quality_assessments.id", ondelete="SET NULL")
    )
    shipment_fingerprint: Mapped[str] = mapped_column(String(64))
    inclusion_status: Mapped[str] = mapped_column(String(20))
    inclusion_reason: Mapped[str] = mapped_column(Text)
    source_provider_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


_CANONICAL_SIGNAL_CHECK = (
    "signal_kind IN ('import_activity','china_dependency','shipping_fit',"
    "'cargo_value_potential','company_scale','growth_signal','contactability',"
    "'logistics_complexity')"
)


class ImportEvidenceSignalPromotionModel(Base):
    __tablename__ = "import_evidence_signal_promotions"
    __table_args__ = (
        CheckConstraint(_CANONICAL_SIGNAL_CHECK, name="ck_import_promotion_signal_kind"),
        CheckConstraint(
            "status IN ('CANDIDATE','PROMOTED','SKIPPED','BLOCKED','SUPERSEDED','FAILED')",
            name="ck_import_promotion_status",
        ),
        CheckConstraint(
            "quality_status IS NULL OR quality_status IN ('VERIFIED','USABLE','REVIEW','REJECTED')",
            name="ck_import_promotion_quality_status",
        ),
        CheckConstraint(
            "quality_score IS NULL OR quality_score BETWEEN 0 AND 100",
            name="ck_import_promotion_quality_score",
        ),
        CheckConstraint(
            "length(trim(input_fingerprint)) > 0",
            name="ck_import_promotion_fingerprint_not_empty",
        ),
        UniqueConstraint(
            "aggregate_id",
            "signal_kind",
            "input_fingerprint",
            name="uq_import_promotion_input",
        ),
        Index(
            "uq_import_promotion_current_company_kind",
            "company_id",
            "signal_kind",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index("ix_import_promotions_aggregate", "aggregate_id"),
        ForeignKeyConstraint(
            ["promoted_signal_id"],
            ["import_evidence_company_signals.id"],
            ondelete="SET NULL",
            name="fk_import_promotion_signal",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["superseded_by_id"],
            ["import_evidence_signal_promotions.id"],
            ondelete="SET NULL",
            name="fk_import_promotion_superseded_by",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    aggregate_id: Mapped[UUID] = mapped_column(
        ForeignKey("importer_evidence_aggregates.id", ondelete="CASCADE")
    )
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    signal_kind: Mapped[str] = mapped_column(String(40))
    signal_detail: Mapped[str] = mapped_column(Text)
    normalized_value_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    source_summary_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    evidence_snapshot_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    quality_status: Mapped[str | None] = mapped_column(String(20))
    quality_score: Mapped[float | None] = mapped_column(Float)
    promotion_version: Mapped[str] = mapped_column(String(64))
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    promoted_signal_id: Mapped[UUID | None] = mapped_column()
    superseded_by_id: Mapped[UUID | None] = mapped_column()
    rejection_reasons_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ImportEvidenceCompanySignalModel(Base):
    __tablename__ = "import_evidence_company_signals"
    __table_args__ = (
        CheckConstraint(_CANONICAL_SIGNAL_CHECK, name="ck_import_projection_signal_kind"),
        CheckConstraint(
            "quality_status IN ('VERIFIED','USABLE')",
            name="ck_import_projection_quality_status",
        ),
        CheckConstraint(
            "quality_score BETWEEN 0 AND 100",
            name="ck_import_projection_quality_score",
        ),
        CheckConstraint(
            "ownership = 'import_evidence'",
            name="ck_import_projection_ownership",
        ),
        UniqueConstraint("promotion_id", name="uq_import_projection_promotion"),
        Index(
            "uq_import_projection_active_company_kind",
            "company_id",
            "signal_kind",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        ForeignKeyConstraint(
            ["promotion_id"],
            ["import_evidence_signal_promotions.id"],
            ondelete="CASCADE",
            name="fk_import_projection_promotion",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["superseded_by_id"],
            ["import_evidence_company_signals.id"],
            ondelete="SET NULL",
            name="fk_import_projection_superseded_by",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    promotion_id: Mapped[UUID] = mapped_column()
    aggregate_id: Mapped[UUID] = mapped_column(
        ForeignKey("importer_evidence_aggregates.id", ondelete="CASCADE")
    )
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    signal_kind: Mapped[str] = mapped_column(String(40))
    signal_detail: Mapped[str] = mapped_column(Text)
    normalized_value_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    provenance_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    quality_status: Mapped[str] = mapped_column(String(20))
    quality_score: Mapped[float] = mapped_column(Float)
    ownership: Mapped[str] = mapped_column(String(30), default="import_evidence")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    superseded_by_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportEvidencePromotionQualityAssessmentModel(Base):
    __tablename__ = "import_evidence_promotion_quality_assessments"

    promotion_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_evidence_signal_promotions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    quality_assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_evidence_quality_assessments.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ImporterEntityMatchModel(Base):
    __tablename__ = "importer_entity_matches"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    shipment_id: Mapped[UUID] = mapped_column(
        ForeignKey("normalized_shipments.id", ondelete="CASCADE")
    )
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    normalized_name: Mapped[str] = mapped_column(String(300))
    match_method: Mapped[str] = mapped_column(String(20))
    match_score: Mapped[float] = mapped_column(Float)
    match_reasons_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    candidate_company_ids_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    review_status: Mapped[str] = mapped_column(String(30))
    reviewed_by: Mapped[UUID | None] = mapped_column()
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ImportEvidenceSignalModel(Base):
    __tablename__ = "import_evidence_signals"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    job_id: Mapped[UUID] = mapped_column(ForeignKey("import_evidence_jobs.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(50))
    raw_record_ids_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    normalized_shipment_ids_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    aggregation_window: Mapped[str] = mapped_column(String(50))
    calculation_method: Mapped[str] = mapped_column(String(50))
    quality_score: Mapped[float] = mapped_column(Float)
    quality_level: Mapped[str] = mapped_column(String(10))
    entity_match_method: Mapped[str] = mapped_column(String(20))
    entity_match_score: Mapped[float] = mapped_column(Float)
    promotion_version: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_evidence_signals_company", "company_id"),)


class ImportEvidenceSnapshotModel(Base):
    __tablename__ = "import_evidence_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("import_evidence_jobs.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(50))
    snapshot_version: Mapped[str] = mapped_column(String(10))
    raw_count: Mapped[int] = mapped_column(Integer, default=0)
    normalized_count: Mapped[int] = mapped_column(Integer, default=0)
    deduped_count: Mapped[int] = mapped_column(Integer, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    promoted_count: Mapped[int] = mapped_column(Integer, default=0)
    data_json: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_evidence_snapshots_company", "company_id"),
        Index("ix_evidence_snapshots_job", "job_id"),
    )


class ImportEvidenceConflictModel(Base):
    __tablename__ = "import_evidence_conflicts"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    signal_ids_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    conflict_type: Mapped[str] = mapped_column(String(100))
    conflict_detail: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(default=False)
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
