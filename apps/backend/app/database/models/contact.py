"""Contact persistence (Discovery context).

Minimal table for now: it gives outreaches.contact_id a real foreign key.
The Contact domain entity (verification lifecycle, provenance) arrives in
a later lesson — this schema only carries what Outreach needs today.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ContactModel(Base):
    __tablename__ = "contacts"
    __table_args__ = (Index("ix_contacts_company_id", "company_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    full_name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(20), default="found")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
