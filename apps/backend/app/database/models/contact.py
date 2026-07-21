"""Contact aggregate persistence (L10): contacts + channels + sources +
append-only fit assessments.

Channels use a natural composite key (contact_id, channel_type,
normalized_value) — duplicate channels are structurally impossible.
Fit assessments are append-only, keyed by (contact_id, fingerprint).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class ContactModel(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('discovered', 'active', 'invalid', 'inactive')",
            name="ck_contacts_status_controlled",
        ),
        Index("ix_contacts_company_id", "company_id"),
        Index("ix_contacts_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200))
    title_raw: Mapped[str | None] = mapped_column(String(200))
    department: Mapped[str] = mapped_column(String(20), default="unknown")
    seniority: Mapped[str] = mapped_column(String(20), default="unknown")
    status: Mapped[str] = mapped_column(String(20), default="discovered")
    invalid_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    channels: Mapped[list["ContactChannelModel"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ContactChannelModel.normalized_value",
    )
    sources: Mapped[list["ContactSourceModel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="ContactSourceModel.position"
    )


class ContactChannelModel(Base):
    __tablename__ = "contact_channels"
    __table_args__ = (
        CheckConstraint(
            "channel_type IN ('email', 'linkedin', 'phone')",
            name="ck_channels_type_controlled",
        ),
        CheckConstraint(
            "verification_status IN "
            "('unverified', 'source_verified', 'manually_verified', 'invalid')",
            name="ck_channels_verification_controlled",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_channels_confidence_range"
        ),
    )

    contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True
    )
    channel_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    normalized_value: Mapped[str] = mapped_column(String(320), primary_key=True)
    display_value: Mapped[str] = mapped_column(String(320))
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified")
    source: Mapped[str] = mapped_column(String(100))
    source_reference: Mapped[str] = mapped_column(Text)
    source_retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(default=0.5)


class ContactSourceModel(Base):
    __tablename__ = "contact_sources"

    contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(100))
    reference: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ContactFitAssessmentModel(Base):
    __tablename__ = "contact_fit_assessments"
    __table_args__ = (
        CheckConstraint(
            "role_fit_score >= 0 AND role_fit_score <= 100",
            name="ck_fit_role_score_range",
        ),
        CheckConstraint(
            "reachability_score >= 0 AND reachability_score <= 100",
            name="ck_fit_reachability_range",
        ),
        CheckConstraint(
            "total_score >= 0 AND total_score <= 100", name="ck_fit_total_range"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_fit_confidence_range"),
        Index("ix_fit_assessments_company_id", "company_id"),
    )

    contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True
    )
    assessment_fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[UUID] = mapped_column()
    role_fit_score: Mapped[float] = mapped_column()
    reachability_score: Mapped[float] = mapped_column()
    total_score: Mapped[float] = mapped_column()
    confidence: Mapped[float] = mapped_column()
    department: Mapped[str] = mapped_column(String(20))
    seniority: Mapped[str] = mapped_column(String(20))
    recommended_channel: Mapped[str | None] = mapped_column(String(20))
    # audit snapshots — never queried relationally
    reasons: Mapped[list[str]] = mapped_column(JSONB)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    policy_version: Mapped[str] = mapped_column(String(50))
    roles_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    normalized_title: Mapped[str | None] = mapped_column(String(300))
    classification_method: Mapped[str | None] = mapped_column(String(30))
    classification_confidence: Mapped[float | None] = mapped_column(Float)
    classification_reasons_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    taxonomy_version: Mapped[str | None] = mapped_column(String(50))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
