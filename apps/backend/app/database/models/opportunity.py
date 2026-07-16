"""Opportunity aggregate persistence: judgments + append-only history.

Assessments and evidence rows are written once and never updated —
database analogue of the domain's append-only history (ADR-0017).
Cross-aggregate references (company_id) are RESTRICTed foreign keys.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class OpportunityModel(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_opportunities_score_range"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_opportunities_confidence_range"
        ),
        Index("ix_opportunities_company_id", "company_id"),
        Index("ix_opportunities_user_id", "user_id"),
        Index("ix_opportunities_stage", "stage"),
        Index("ix_opportunities_priority", "priority"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    user_id: Mapped[UUID] = mapped_column()  # Identity context — no users table yet (L5 trade-off)
    stage: Mapped[str] = mapped_column(String(20))
    stage_reason: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column()
    confidence: Mapped[float | None] = mapped_column()
    priority: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    assessments: Mapped[list["OpportunityAssessmentModel"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OpportunityAssessmentModel.position",
    )


class OpportunityAssessmentModel(Base):
    __tablename__ = "opportunity_assessments"
    __table_args__ = (
        CheckConstraint(
            "new_score >= 0 AND new_score <= 100", name="ck_assessments_new_score_range"
        ),
        CheckConstraint(
            "old_score IS NULL OR (old_score >= 0 AND old_score <= 100)",
            name="ck_assessments_old_score_range",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_assessments_confidence_range"
        ),
    )

    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(primary_key=True)
    old_score: Mapped[float | None] = mapped_column()
    new_score: Mapped[float] = mapped_column()
    confidence: Mapped[float] = mapped_column()
    reasons: Mapped[list[str]] = mapped_column(JSONB)  # display-only, never searched
    priority: Mapped[str | None] = mapped_column(String(10))
    recommended_action: Mapped[str | None] = mapped_column(Text)
    assessed_by: Mapped[str | None] = mapped_column(String(100))
    scoring_version: Mapped[str] = mapped_column(String(50))
    user_lens_version: Mapped[str | None] = mapped_column(String(50))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    evidence: Mapped[list["OpportunityEvidenceModel"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OpportunityEvidenceModel.position",
    )


class OpportunityEvidenceModel(Base):
    __tablename__ = "opportunity_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["opportunity_id", "assessment_position"],
            ["opportunity_assessments.opportunity_id", "opportunity_assessments.position"],
            ondelete="CASCADE",
        ),
    )

    opportunity_id: Mapped[UUID] = mapped_column(primary_key=True)
    assessment_position: Mapped[int] = mapped_column(primary_key=True)
    position: Mapped[int] = mapped_column(primary_key=True)
    claim: Mapped[str] = mapped_column(Text)
    # provenance blob {source, reference, retrieved_at} — audit display, never queried
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
