"""Import evidence persistence: append-only raw records, normalized shipments, entity matches, signals, conflicts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
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
            "provider", "provider_record_id", "raw_payload_hash",
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
    dedupe_method: Mapped[str] = mapped_column(String(20), default="fingerprint")
    dedupe_reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_record_ids_json: Mapped[list[str]] = mapped_column(JSONB, default=list)


class ImporterEntityMatchModel(Base):
    __tablename__ = "importer_entity_matches"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    shipment_id: Mapped[UUID] = mapped_column(ForeignKey("normalized_shipments.id", ondelete="CASCADE"))
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

    __table_args__ = (
        Index("ix_evidence_signals_company", "company_id"),
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
