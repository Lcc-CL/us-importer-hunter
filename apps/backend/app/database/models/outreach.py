"""Outreach aggregate persistence: conversation, drafts and outcomes.

Draft content and outcomes are append-only. Human approval updates only the
draft's approval metadata; it never rewrites generated subject/body content.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class OutreachModel(Base):
    __tablename__ = "outreaches"
    __table_args__ = (
        Index("ix_outreaches_opportunity_id", "opportunity_id"),
        Index("ix_outreaches_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    opportunity_id: Mapped[UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="RESTRICT")
    )
    contact_id: Mapped[UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20))
    approved_version: Mapped[int | None] = mapped_column()
    sent_version: Mapped[int | None] = mapped_column()
    follow_up_active: Mapped[bool] = mapped_column(default=True)
    closed_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    drafts: Mapped[list["EmailDraftModel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="EmailDraftModel.version"
    )
    outcomes: Mapped[list["OutcomeModel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="OutcomeModel.position"
    )


class EmailDraftModel(Base):
    __tablename__ = "email_drafts"
    __table_args__ = (
        CheckConstraint("subject <> ''", name="ck_drafts_subject_not_empty"),
        CheckConstraint("body <> ''", name="ck_drafts_body_not_empty"),
        CheckConstraint(
            "approval_status IN ('generated', 'approved', 'rejected')",
            name="ck_drafts_approval_status_controlled",
        ),
        # same facts + same prompt never drafted twice (pre-L11 rows have '')
        Index(
            "uq_drafts_context_prompt",
            "outreach_id",
            "context_fingerprint",
            "prompt_version",
            unique=True,
            postgresql_where="context_fingerprint <> ''",
        ),
    )

    outreach_id: Mapped[UUID] = mapped_column(
        ForeignKey("outreaches.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    approval_status: Mapped[str] = mapped_column(String(20), default="generated")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_name: Mapped[str | None] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(50), default="unknown")
    model: Mapped[str] = mapped_column(String(100), default="unknown")
    prompt_version: Mapped[str] = mapped_column(String(50))
    context_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OutcomeModel(Base):
    __tablename__ = "outcomes"

    outreach_id: Mapped[UUID] = mapped_column(
        ForeignKey("outreaches.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str] = mapped_column(Text)
    draft_version: Mapped[int | None] = mapped_column()
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
