"""Persistence models for auditable Umail CSV exports and suppression."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
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


class SuppressionEntryModel(Base):
    __tablename__ = "suppression_entries"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(email, domain, company) = 1",
            name="ck_suppression_entries_single_target",
        ),
        CheckConstraint(
            "(active AND deactivated_by IS NULL AND deactivated_at IS NULL) OR "
            "(NOT active AND deactivated_by IS NOT NULL AND deactivated_at IS NOT NULL)",
            name="ck_suppression_entries_deactivation_audit",
        ),
        Index("ix_suppression_entries_active_email", "active", "email"),
        Index("ix_suppression_entries_active_domain", "active", "domain"),
        Index("ix_suppression_entries_active_company", "active", "company"),
        Index("ix_suppression_entries_created", "created_at"),
        Index(
            "uq_suppression_entries_active_email",
            "email",
            unique=True,
            postgresql_where=text("active AND email IS NOT NULL"),
        ),
        Index(
            "uq_suppression_entries_active_domain",
            "domain",
            unique=True,
            postgresql_where=text("active AND domain IS NOT NULL"),
        ),
        Index(
            "uq_suppression_entries_active_company",
            "company",
            unique=True,
            postgresql_where=text("active AND company IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320))
    domain: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    deactivated_by: Mapped[str | None] = mapped_column(String(160))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UmailExportBatchModel(Base):
    __tablename__ = "umail_export_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('prepared','downloaded')",
            name="ck_umail_export_batches_status",
        ),
        CheckConstraint(
            "execution_generation > 0",
            name="ck_umail_export_batches_generation",
        ),
        CheckConstraint(
            "total_rows >= 0 AND ready_count >= 0 AND suppressed_count >= 0 "
            "AND invalid_count >= 0 AND duplicate_count >= 0",
            name="ck_umail_export_batches_counts_nonnegative",
        ),
        CheckConstraint(
            "ready_count + suppressed_count + invalid_count + duplicate_count = total_rows",
            name="ck_umail_export_batches_counts_sum",
        ),
        CheckConstraint(
            "(status = 'prepared' AND downloaded_at IS NULL) OR "
            "(status = 'downloaded' AND downloaded_at IS NOT NULL)",
            name="ck_umail_export_batches_downloaded_at",
        ),
        UniqueConstraint("selection_hash", name="uq_umail_export_batches_selection_hash"),
        Index(
            "ix_umail_export_batches_run_generation_created",
            "routing_run_id",
            "execution_generation",
            "created_at",
        ),
        Index("ix_umail_export_batches_status_updated", "status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    routing_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("prospect_routing_runs.id", ondelete="RESTRICT"), nullable=False
    )
    execution_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    campaign: Mapped[str] = mapped_column(String(200), nullable=False)
    mapping_version: Mapped[str] = mapped_column(String(80), nullable=False)
    selection_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False)
    suppressed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    invalid_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UmailExportRowModel(Base):
    __tablename__ = "umail_export_rows"
    __table_args__ = (
        CheckConstraint("position > 0", name="ck_umail_export_rows_position"),
        CheckConstraint(
            "route = 'B'", name="ck_umail_export_rows_effective_b"
        ),
        CheckConstraint(
            "route_review_status IN ('confirmed','overridden')",
            name="ck_umail_export_rows_reviewed",
        ),
        CheckConstraint(
            "pre_score >= 0 AND pre_score <= 100",
            name="ck_umail_export_rows_score",
        ),
        CheckConstraint(
            "status IN ('ready','suppressed','invalid','duplicate')",
            name="ck_umail_export_rows_status",
        ),
        CheckConstraint(
            "(status = 'ready' AND email IS NOT NULL AND exclusion_reason IS NULL) OR "
            "(status <> 'ready' AND exclusion_reason IS NOT NULL)",
            name="ck_umail_export_rows_exclusion_reason",
        ),
        UniqueConstraint("batch_id", "position", name="uq_umail_export_rows_position"),
        UniqueConstraint(
            "batch_id", "row_fingerprint", name="uq_umail_export_rows_fingerprint"
        ),
        Index("ix_umail_export_rows_batch_status", "batch_id", "status", "position"),
        Index("ix_umail_export_rows_batch_company", "batch_id", "company_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("umail_export_batches.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    company_id: Mapped[UUID] = mapped_column(nullable=False)
    contact_id: Mapped[UUID | None] = mapped_column()
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    company_website: Mapped[str | None] = mapped_column(String(2048))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    first_name: Mapped[str | None] = mapped_column(String(200))
    last_name: Mapped[str | None] = mapped_column(String(200))
    contact_title: Mapped[str | None] = mapped_column(String(200))
    contact_role: Mapped[str | None] = mapped_column(String(40))
    contact_seniority: Mapped[str | None] = mapped_column(String(40))
    is_department_contact: Mapped[bool] = mapped_column(Boolean, nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(320))
    country: Mapped[str | None] = mapped_column(String(100))
    route: Mapped[str] = mapped_column(String(1), nullable=False)
    route_review_status: Mapped[str] = mapped_column(String(20), nullable=False)
    pre_score: Mapped[float] = mapped_column(Float, nullable=False)
    route_reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(Text)
    row_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
