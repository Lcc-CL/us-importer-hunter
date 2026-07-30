"""Persistence for discovery task details and provider candidates."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class DiscoveryTaskModel(Base):
    __tablename__ = "discovery_tasks"
    __table_args__ = (
        CheckConstraint("requested_count > 0", name="ck_discovery_tasks_requested_positive"),
        CheckConstraint("effective_count > 0", name="ck_discovery_tasks_effective_positive"),
        CheckConstraint(
            "effective_count <= requested_count",
            name="ck_discovery_tasks_effective_lte_requested",
        ),
        CheckConstraint(
            "provider_failure_count >= 0",
            name="ck_discovery_tasks_provider_failures_nonnegative",
        ),
        CheckConstraint(
            "status IN ('pending','running','completed','partial_failed','failed')",
            name="ck_discovery_tasks_status",
        ),
        Index("ix_discovery_tasks_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    original_prompt: Mapped[str] = mapped_column(Text)
    requested_count: Mapped[int] = mapped_column(Integer)
    effective_count: Mapped[int] = mapped_column(Integer)
    parsed_region: Mapped[str] = mapped_column(String(100))
    parsed_category: Mapped[str] = mapped_column(String(100))
    parsed_keywords: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    provider_failure_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    candidates: Mapped[list["DiscoveryCandidateModel"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DiscoveryCandidateModel.created_at",
    )


class DiscoveryCandidateModel(Base):
    __tablename__ = "discovery_task_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('discovered','ingested','duplicate','failed')",
            name="ck_discovery_candidates_status",
        ),
        Index("ix_discovery_candidates_task_status", "task_id", "status"),
        Index("ix_discovery_candidates_domain", "normalized_domain"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_tasks.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(Text)
    company_name: Mapped[str] = mapped_column(Text)
    normalized_name: Mapped[str] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    normalized_domain: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    product_description: Mapped[str | None] = mapped_column(Text)
    import_evidence: Mapped[str | None] = mapped_column(Text)
    raw_metadata_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30))
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL")
    )
    duplicate_of_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("discovery_task_candidates.id", ondelete="SET NULL")
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
