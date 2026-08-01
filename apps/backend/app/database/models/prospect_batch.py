"""Persistence models for D2 batch orchestration state."""

from datetime import datetime
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class ProspectBatchModel(Base):
    __tablename__ = "prospect_batches"
    __table_args__ = (
        CheckConstraint("requested_count > 0", name="ck_prospect_batches_requested_positive"),
        CheckConstraint(
            "effective_count > 0 AND effective_count <= 5",
            name="ck_prospect_batches_effective_range",
        ),
        CheckConstraint(
            "effective_count <= requested_count", name="ck_prospect_batches_effective_lte_requested"
        ),
        CheckConstraint(
            "status IN ('pending','running','completed','partial_failed','failed')",
            name="ck_prospect_batches_status",
        ),
        Index("ix_prospect_batches_discovery_task", "discovery_task_id", "created_at"),
        Index("ix_prospect_batches_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    discovery_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_tasks.id", ondelete="CASCADE"), nullable=False
    )
    requested_count: Mapped[int] = mapped_column(Integer)
    effective_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30))
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    companies: Mapped[list["ProspectBatchCompanyModel"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProspectBatchCompanyModel.position",
    )


class ProspectBatchCompanyModel(Base):
    __tablename__ = "prospect_batch_companies"
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_prospect_batch_companies_position"),
        CheckConstraint(
            "blocking_claim_count >= 0",
            name="ck_prospect_batch_companies_blocking_claim_count",
        ),
        CheckConstraint(
            "resume_count >= 0",
            name="ck_prospect_batch_companies_resume_count",
        ),
        CheckConstraint(
            "current_stage IN ('queued','validating','researching','awaiting_evidence_review',"
            "'scoring','discovering_contact','generating_draft','completed','needs_review','failed')",
            name="ck_prospect_batch_companies_stage",
        ),
        CheckConstraint(
            "status IN ('queued','running','completed','needs_review','failed')",
            name="ck_prospect_batch_companies_status",
        ),
        UniqueConstraint("batch_id", "position", name="uq_prospect_batch_position"),
        Index("ix_prospect_batch_companies_status", "batch_id", "status"),
        Index(
            "ix_prospect_batch_company_pipeline",
            "company_id",
            "pipeline_version",
        ),
    )

    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("prospect_batches.id", ondelete="CASCADE"), primary_key=True
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), primary_key=True
    )
    company_name: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)
    pipeline_version: Mapped[str] = mapped_column(String(80))
    current_stage: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30))
    research_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_runs.id", ondelete="SET NULL")
    )
    opportunity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL")
    )
    selected_contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL")
    )
    outreach_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("outreaches.id", ondelete="SET NULL")
    )
    draft_version: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[float | None] = mapped_column()
    qualification_decision: Mapped[str | None] = mapped_column(String(30))
    reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    contact_name: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(Text)
    contact_source_url: Mapped[str | None] = mapped_column(Text)
    draft_subject: Mapped[str | None] = mapped_column(Text)
    draft_status: Mapped[str | None] = mapped_column(String(30))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blocking_claim_count: Mapped[int] = mapped_column(Integer, default=0)
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resumed_from_stage: Mapped[str | None] = mapped_column(String(40))
    resume_count: Mapped[int] = mapped_column(Integer, default=0)
