"""Persistence models for offline Umail feedback and engagement events."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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


class UmailResultImportModel(Base):
    __tablename__ = "umail_result_imports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploaded','parsed','ready_for_review','applied',"
            "'partial_applied','failed')",
            name="ck_umail_result_imports_status",
        ),
        CheckConstraint(
            "input_row_count >= 0 AND matched_count >= 0 AND unmatched_count >= 0 "
            "AND ambiguous_count >= 0 AND invalid_count >= 0 AND duplicate_count >= 0 "
            "AND projected_event_count >= 0 AND projected_suppression_count >= 0 "
            "AND applied_event_count >= 0 AND suppression_created_count >= 0",
            name="ck_umail_result_imports_counts_nonnegative",
        ),
        CheckConstraint(
            "matched_count + unmatched_count + ambiguous_count + invalid_count + "
            "duplicate_count = input_row_count",
            name="ck_umail_result_imports_counts_sum",
        ),
        CheckConstraint(
            "projected_event_count = matched_count AND "
            "projected_suppression_count <= projected_event_count",
            name="ck_umail_result_imports_projected_counts",
        ),
        CheckConstraint(
            "(status IN ('applied','partial_applied') AND applied_at IS NOT NULL) OR "
            "(status NOT IN ('applied','partial_applied') AND applied_at IS NULL)",
            name="ck_umail_result_imports_applied_at",
        ),
        UniqueConstraint(
            "file_sha256",
            "mapping_version",
            name="uq_umail_result_imports_file_mapping",
        ),
        Index("ix_umail_result_imports_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_version: Mapped[str] = mapped_column(String(80), nullable=False)
    mapping_snapshot_json: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    input_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unmatched_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ambiguous_count: Mapped[int] = mapped_column(Integer, nullable=False)
    invalid_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    projected_event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    projected_suppression_count: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    suppression_created_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(Text)


class UmailResultRowModel(Base):
    __tablename__ = "umail_result_rows"
    __table_args__ = (
        CheckConstraint("row_number >= 2", name="ck_umail_result_rows_number"),
        CheckConstraint(
            "match_status IN ('matched','unmatched','ambiguous','invalid','duplicate')",
            name="ck_umail_result_rows_match_status",
        ),
        CheckConstraint(
            "canonical_event_type IS NULL OR canonical_event_type IN "
            "('sent','delivered','hard_bounced','soft_bounced','bounce_unknown',"
            "'unsubscribed','complained','replied','opened','clicked')",
            name="ck_umail_result_rows_event_type",
        ),
        CheckConstraint(
            "(match_status = 'matched' AND matched_export_row_id IS NOT NULL "
            "AND match_method IS NOT NULL AND canonical_event_type IS NOT NULL "
            "AND occurred_at IS NOT NULL) OR "
            "(match_status <> 'matched' AND matched_export_row_id IS NULL)",
            name="ck_umail_result_rows_match_audit",
        ),
        UniqueConstraint(
            "result_import_id", "row_number", name="uq_umail_result_rows_import_number"
        ),
        UniqueConstraint(
            "result_import_id",
            "row_fingerprint",
            name="uq_umail_result_rows_import_fingerprint",
        ),
        Index(
            "ix_umail_result_rows_import_match",
            "result_import_id",
            "match_status",
            "row_number",
        ),
        Index(
            "ix_umail_result_rows_import_event",
            "result_import_id",
            "canonical_event_type",
            "row_number",
        ),
        Index("ix_umail_result_rows_matched_export", "matched_export_row_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    result_import_id: Mapped[UUID] = mapped_column(
        ForeignKey("umail_result_imports.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    export_batch_id: Mapped[UUID | None] = mapped_column()
    export_row_id: Mapped[UUID | None] = mapped_column()
    normalized_email: Mapped[str | None] = mapped_column(String(320))
    campaign: Mapped[str | None] = mapped_column(String(200))
    canonical_event_type: Mapped[str | None] = mapped_column(String(30))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bounce_type: Mapped[str | None] = mapped_column(String(80))
    message_id: Mapped[str | None] = mapped_column(String(500))
    match_status: Mapped[str] = mapped_column(String(20), nullable=False)
    matched_export_row_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("umail_export_rows.id", ondelete="RESTRICT")
    )
    match_method: Mapped[str | None] = mapped_column(String(40))
    error_codes_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    row_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ContactEngagementEventModel(Base):
    __tablename__ = "contact_engagement_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('sent','delivered','hard_bounced','soft_bounced',"
            "'bounce_unknown','unsubscribed','complained','replied','opened','clicked')",
            name="ck_contact_engagement_events_type",
        ),
        UniqueConstraint(
            "event_fingerprint", name="uq_contact_engagement_events_fingerprint"
        ),
        Index("ix_contact_engagement_events_import_time", "result_import_id", "occurred_at"),
        Index("ix_contact_engagement_events_contact_time", "contact_id", "occurred_at"),
        Index("ix_contact_engagement_events_company_time", "company_id", "occurred_at"),
        Index("ix_contact_engagement_events_campaign_type", "campaign", "event_type"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    result_import_id: Mapped[UUID] = mapped_column(
        ForeignKey("umail_result_imports.id", ondelete="RESTRICT"), nullable=False
    )
    result_row_id: Mapped[UUID] = mapped_column(
        ForeignKey("umail_result_rows.id", ondelete="RESTRICT"), nullable=False
    )
    export_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("umail_export_batches.id", ondelete="RESTRICT"), nullable=False
    )
    export_row_id: Mapped[UUID] = mapped_column(
        ForeignKey("umail_export_rows.id", ondelete="RESTRICT"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    campaign: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    event_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
