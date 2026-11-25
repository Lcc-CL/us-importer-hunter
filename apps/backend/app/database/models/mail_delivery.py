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
        CheckConstraint(
            "(approved_issuer IS NULL) = (approved_subject IS NULL)",
            name="ck_mail_campaign_approved_identity",
        ),
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
    approved_issuer: Mapped[str | None] = mapped_column(Text)
    approved_subject: Mapped[str | None] = mapped_column(String(255))


class MailCampaignAuditModel(Base):
    __tablename__ = "mail_campaign_audit"
    __table_args__ = (
        CheckConstraint(
            "action IN ('create', 'approve', 'pause', 'resume', 'cancel')",
            name="ck_mail_campaign_audit_action",
        ),
        CheckConstraint(
            "(actor_issuer IS NULL) = (actor_subject IS NULL)",
            name="ck_mail_campaign_audit_identity",
        ),
        Index("ix_mail_campaign_audit_page", "campaign_id", "occurred_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("mail_campaigns.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(16))
    actor_name: Mapped[str] = mapped_column(String(160))
    actor_issuer: Mapped[str | None] = mapped_column(Text)
    actor_subject: Mapped[str | None] = mapped_column(String(255))
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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


class MailDeliveryReconciliationModel(Base):
    """Immutable operator evidence, one decision per delivery attempt."""

    __tablename__ = "mail_delivery_reconciliations"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('accepted', 'not_submitted')",
            name="ck_mail_reconciliation_decision",
        ),
        CheckConstraint("attempt > 0", name="ck_mail_reconciliation_attempt"),
    )

    delivery_id: Mapped[UUID] = mapped_column(
        ForeignKey("mail_deliveries.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    attempt: Mapped[int] = mapped_column(primary_key=True)
    decision: Mapped[str] = mapped_column(String(16))
    provider_reference: Mapped[str] = mapped_column(String(256))
    note: Mapped[str] = mapped_column(Text)
    actor_name: Mapped[str] = mapped_column(String(160))
    actor_issuer: Mapped[str] = mapped_column(Text)
    actor_subject: Mapped[str] = mapped_column(String(255))
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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
