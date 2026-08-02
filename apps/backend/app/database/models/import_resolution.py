"""Persistence models for D5b1 import entity resolution and processing jobs."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ImportResolutionModel(Base):
    __tablename__ = "import_resolutions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','partial_failed','failed')",
            name="ck_import_resolutions_status",
        ),
        CheckConstraint("total_rows >= 0", name="ck_import_resolutions_total_rows"),
        CheckConstraint("processed_rows >= 0", name="ck_import_resolutions_processed_rows"),
        CheckConstraint("processed_rows <= total_rows", name="ck_import_resolutions_processed_lte"),
        CheckConstraint("companies_created >= 0", name="ck_import_resolutions_companies_created"),
        CheckConstraint("companies_reused >= 0", name="ck_import_resolutions_companies_reused"),
        CheckConstraint("company_reviews_required >= 0", name="ck_import_resolutions_reviews"),
        CheckConstraint("contacts_created >= 0", name="ck_import_resolutions_contacts_created"),
        CheckConstraint("contacts_reused >= 0", name="ck_import_resolutions_contacts_reused"),
        CheckConstraint(
            "company_contacts_created >= 0", name="ck_import_resolutions_links_created"
        ),
        CheckConstraint("invalid_rows >= 0", name="ck_import_resolutions_invalid_rows"),
        CheckConstraint("failed_rows >= 0", name="ck_import_resolutions_failed_rows"),
        Index("ix_import_resolutions_status_updated", "status", "updated_at"),
    )

    import_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    companies_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    companies_reused: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    company_reviews_required: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contacts_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contacts_reused: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    company_contacts_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CompanyExternalIdentityModel(Base):
    __tablename__ = "company_external_identities"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_company_external_identity"),
        Index("ix_company_external_identities_company", "company_id"),
        Index("ix_company_external_identities_source_external", "source", "external_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CompanyResolutionProfileModel(Base):
    __tablename__ = "company_resolution_profiles"
    __table_args__ = (
        Index("ix_company_resolution_profiles_domain", "normalized_domain"),
        Index(
            "ix_company_resolution_profiles_name_address",
            "normalized_name",
            "normalized_address",
        ),
    )

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    normalized_name: Mapped[str] = mapped_column(String(240), nullable=False)
    normalized_domain: Mapped[str | None] = mapped_column(String(255))
    normalized_address: Mapped[str | None] = mapped_column(Text)
    company_type: Mapped[str | None] = mapped_column(String(100))
    normalized_phone: Mapped[str | None] = mapped_column(String(40))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_import_row_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("raw_import_rows.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CompanyContactModel(Base):
    __tablename__ = "company_contacts"
    __table_args__ = (
        CheckConstraint(
            "role_category IN ('owner_founder','executive','procurement','supply_chain',"
            "'logistics','operations','import_export','warehouse','sales',"
            "'general_department','irrelevant','unknown')",
            name="ck_company_contacts_role_category",
        ),
        CheckConstraint(
            "seniority IN ('c_level','vp','director','head','manager','specialist','unknown')",
            name="ck_company_contacts_seniority",
        ),
        CheckConstraint(
            "status IN ('active','inactive','unknown')",
            name="ck_company_contacts_status",
        ),
        UniqueConstraint("company_id", "contact_id", name="uq_company_contacts_employment"),
        Index("ix_company_contacts_company", "company_id"),
        Index("ix_company_contacts_contact", "contact_id"),
        Index("ix_company_contacts_role", "company_id", "role_category", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    raw_title: Mapped[str | None] = mapped_column(Text)
    role_category: Mapped[str] = mapped_column(String(40), nullable=False)
    seniority: Mapped[str] = mapped_column(String(20), nullable=False)
    is_department_contact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_import_row_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("raw_import_rows.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImportEntityDecisionModel(Base):
    __tablename__ = "import_entity_decisions"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('company','contact')",
            name="ck_import_entity_decisions_entity_type",
        ),
        CheckConstraint(
            "decision IN ('auto_create','auto_merge','review_required','manual_merge',"
            "'keep_separate','rejected')",
            name="ck_import_entity_decisions_decision",
        ),
        CheckConstraint(
            "review_status IN ('not_required','pending','reviewed')",
            name="ck_import_entity_decisions_review_status",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_import_entity_decisions_confidence",
        ),
        UniqueConstraint(
            "import_session_id",
            "raw_import_row_id",
            "entity_type",
            name="uq_import_entity_decisions_row_type",
        ),
        Index(
            "ix_import_entity_decisions_review",
            "import_session_id",
            "review_status",
            "entity_type",
        ),
        Index("ix_import_entity_decisions_candidate", "candidate_entity_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    import_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_sessions.id", ondelete="CASCADE"), nullable=False
    )
    raw_import_row_id: Mapped[UUID] = mapped_column(
        ForeignKey("raw_import_rows.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    candidate_entity_id: Mapped[UUID | None] = mapped_column()
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    review_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(160))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImportProcessingJobModel(Base):
    __tablename__ = "import_processing_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','leased','running','completed','failed','cancelled')",
            name="ck_import_processing_jobs_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_import_processing_jobs_attempts"),
        CheckConstraint("max_attempts > 0", name="ck_import_processing_jobs_max_attempts"),
        CheckConstraint("recovery_count >= 0", name="ck_import_processing_jobs_recovery"),
        Index(
            "uq_import_processing_jobs_active_business",
            "business_key",
            unique=True,
            postgresql_where=text("status IN ('pending','leased','running')"),
        ),
        Index("ix_import_processing_jobs_claim", "status", "available_at", "created_at"),
        Index("ix_import_processing_jobs_session", "import_session_id", "created_at"),
        Index("ix_import_processing_jobs_lease_expiry", "lease_expires_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    import_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_sessions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    business_key: Mapped[str] = mapped_column(String(64), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    lease_acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_summary: Mapped[str | None] = mapped_column(Text)
    recovery_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
