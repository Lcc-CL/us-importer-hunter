"""Company aggregate persistence: companies + owned child tables.

Child rows use deterministic composite keys so saves (session.merge)
diff instead of duplicating. Deletes cascade inside the aggregate only.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class CompanyModel(Base):
    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_companies_normalized_name", "normalized_name"),
        Index("ix_companies_website_host", "website_host"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200))
    website: Mapped[str | None] = mapped_column(String(2048))
    website_host: Mapped[str | None] = mapped_column(String(255))
    verified: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    aliases: Mapped[list["CompanyAliasModel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="CompanyAliasModel.normalized_name"
    )
    sources: Mapped[list["CompanySourceModel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="CompanySourceModel.position"
    )
    signals: Mapped[list["CompanySignalModel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="CompanySignalModel.position"
    )


class CompanyAliasModel(Base):
    __tablename__ = "company_aliases"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    normalized_name: Mapped[str] = mapped_column(String(200), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))


class CompanySourceModel(Base):
    __tablename__ = "company_sources"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(100))
    reference: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CompanySignalModel(Base):
    __tablename__ = "company_signals"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(primary_key=True)
    signal: Mapped[str] = mapped_column(Text)
