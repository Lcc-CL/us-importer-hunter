"""The latest reservation or observed activity for each channel source."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ContactTouchModel(Base):
    __tablename__ = "contact_touches"
    __table_args__ = (
        CheckConstraint("channel IN ('smtp', 'umail')", name="ck_contact_touch_channel"),
        CheckConstraint(
            "(state = 'reserved' AND reserved_at IS NOT NULL AND confirmed_at IS NULL) OR "
            "(state = 'confirmed' AND confirmed_at IS NOT NULL) OR "
            "(channel = 'smtp' AND state IN ('unknown', 'released') "
            "AND reserved_at IS NOT NULL AND confirmed_at IS NULL)",
            name="ck_contact_touch_state",
        ),
        Index("ix_contact_touches_recipient", "recipient"),
    )

    channel: Mapped[str] = mapped_column(String(8), primary_key=True)
    source_id: Mapped[UUID] = mapped_column(primary_key=True)
    recipient: Mapped[str] = mapped_column(String(320))
    state: Mapped[str] = mapped_column(String(12))
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
