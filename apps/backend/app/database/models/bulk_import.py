"""Persistence models for traceable raw CSV intake."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
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


class ImportSessionModel(Base):
    __tablename__ = "import_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('receiving','processing','completed','partial_failed','failed')",
            name="ck_import_sessions_status",
        ),
        CheckConstraint("file_size_bytes > 0", name="ck_import_sessions_file_size_positive"),
        CheckConstraint("total_rows >= 0", name="ck_import_sessions_total_nonnegative"),
        CheckConstraint("accepted_rows >= 0", name="ck_import_sessions_accepted_nonnegative"),
        CheckConstraint("invalid_rows >= 0", name="ck_import_sessions_invalid_nonnegative"),
        CheckConstraint("duplicate_rows >= 0", name="ck_import_sessions_duplicate_nonnegative"),
        CheckConstraint(
            "accepted_rows + invalid_rows + duplicate_rows = total_rows",
            name="ck_import_sessions_counts_sum",
        ),
        UniqueConstraint("source", "file_sha256", name="uq_import_sessions_source_hash"),
        Index("ix_import_sessions_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    encoding: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RawImportRowModel(Base):
    __tablename__ = "raw_import_rows"
    __table_args__ = (
        CheckConstraint("row_number >= 2", name="ck_raw_import_rows_number"),
        CheckConstraint(
            "status IN ('accepted','invalid','duplicate')",
            name="ck_raw_import_rows_status",
        ),
        UniqueConstraint(
            "import_session_id", "row_number", name="uq_raw_import_rows_session_number"
        ),
        Index("ix_raw_import_rows_session_status", "import_session_id", "status"),
        Index("ix_raw_import_rows_session_hash", "import_session_id", "row_hash"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    import_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_sessions.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_codes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
