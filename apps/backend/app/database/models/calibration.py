"""Persistence for D4a calibration runs and human evaluations."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class CalibrationRunModel(Base):
    __tablename__ = "calibration_runs"
    __table_args__ = (
        CheckConstraint("sample_count BETWEEN 3 AND 5", name="ck_calibration_sample_range"),
        CheckConstraint(
            "website_fetch_mode IN ('real_http','fixture')",
            name="ck_calibration_website_fetch_mode",
        ),
        CheckConstraint(
            "research_provider_mode IN ('real','deterministic_fake')",
            name="ck_calibration_research_provider_mode",
        ),
        CheckConstraint(
            "draft_provider_mode IN ('real','deterministic_fake')",
            name="ck_calibration_draft_provider_mode",
        ),
        CheckConstraint(
            "contact_source_mode = 'official_website'",
            name="ck_calibration_contact_source_mode",
        ),
        UniqueConstraint("prospect_batch_id", name="uq_calibration_prospect_batch"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    discovery_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_tasks.id", ondelete="CASCADE"), nullable=False
    )
    prospect_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("prospect_batches.id", ondelete="CASCADE"), nullable=False
    )
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    website_fetch_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    research_provider_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    draft_provider_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    contact_source_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    evaluations: Mapped[list["CalibrationEvaluationModel"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CalibrationEvaluationModel.company_id",
    )


class CalibrationEvaluationModel(Base):
    __tablename__ = "calibration_evaluations"
    __table_args__ = (
        CheckConstraint(
            "research_accuracy BETWEEN 1 AND 5",
            name="ck_calibration_eval_research_range",
        ),
        CheckConstraint(
            "opportunity_reasonableness BETWEEN 1 AND 5",
            name="ck_calibration_eval_opportunity_range",
        ),
        CheckConstraint(
            "contact_usability BETWEEN 1 AND 5",
            name="ck_calibration_eval_contact_range",
        ),
        CheckConstraint(
            "draft_personalization BETWEEN 1 AND 5",
            name="ck_calibration_eval_personalization_range",
        ),
        CheckConstraint(
            "draft_professionalism BETWEEN 1 AND 5",
            name="ck_calibration_eval_professionalism_range",
        ),
    )

    calibration_id: Mapped[UUID] = mapped_column(
        ForeignKey("calibration_runs.id", ondelete="CASCADE"), primary_key=True
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), primary_key=True
    )
    research_accuracy: Mapped[int] = mapped_column(Integer, nullable=False)
    opportunity_reasonableness: Mapped[int] = mapped_column(Integer, nullable=False)
    contact_usability: Mapped[int] = mapped_column(Integer, nullable=False)
    draft_personalization: Mapped[int] = mapped_column(Integer, nullable=False)
    draft_professionalism: Mapped[int] = mapped_column(Integer, nullable=False)
    ready_for_real_outreach: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reviewer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
