"""Durable campaign snapshots and PostgreSQL delivery queue."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class MailCampaignModel(Base):
    __tablename__ = "mail_campaigns"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'cancelled')",
            name="ck_mail_campaign_status",
        ),
        Index("ix_mail_campaign_created", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(16))
    request_hash: Mapped[str] = mapped_column(String(64))
    sender_hash: Mapped[str] = mapped_column(String(64))
    sender_address: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(160))


class MailDeliveryModel(Base):
    __tablename__ = "mail_deliveries"
    __table_args__ = (
        UniqueConstraint("campaign_id", "recipient", name="uq_mail_campaign_recipient"),
        CheckConstraint(
            "status IN ('pending', 'sending', 'accepted', 'failed', 'unknown', 'suppressed')",
            name="ck_mail_delivery_status",
        ),
        Index(
            "ix_mail_delivery_claim",
            "available_at",
            "id",
            postgresql_where="status = 'pending'",
        ),
        Index(
            "ix_mail_delivery_expired",
            "lease_until",
            "id",
            postgresql_where="status = 'sending'",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("mail_campaigns.id", ondelete="RESTRICT"))
    company_id: Mapped[UUID] = mapped_column()
    source_key: Mapped[str] = mapped_column(String(100))
    recipient: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    attempt: Mapped[int] = mapped_column()
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_code: Mapped[str | None] = mapped_column(String(40))


class MailSourceReservationModel(Base):
    """Reserve a source only immediately before its first dispatch."""

    __tablename__ = "mail_source_reservations"

    source_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    delivery_id: Mapped[UUID] = mapped_column(ForeignKey("mail_deliveries.id", ondelete="RESTRICT"))


class MailRateGateModel(Base):
    __tablename__ = "mail_rate_gate"

    id: Mapped[int] = mapped_column(primary_key=True)
    next_slot: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MailFeedbackModel(Base):
    __tablename__ = "mail_feedback"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('delivered', 'hard_bounced', 'unsubscribed', 'complained')",
            name="ck_mail_feedback_kind",
        ),
        Index("ix_mail_feedback_delivery", "delivery_id"),
    )

    event_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    delivery_id: Mapped[UUID] = mapped_column(ForeignKey("mail_deliveries.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(20))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
