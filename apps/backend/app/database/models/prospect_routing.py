"""Persistence models for deterministic prospect routing."""

from datetime import datetime
from typing import Any
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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ProspectRoutingRunModel(Base):
    __tablename__ = "prospect_routing_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','partial_completed','failed')",
            name="ck_prospect_routing_runs_status",
        ),
        CheckConstraint(
            "execution_generation > 0",
            name="ck_prospect_routing_runs_generation",
        ),
        CheckConstraint(
            "total_companies >= 0 AND routed_companies >= 0 AND blocked_companies >= 0",
            name="ck_prospect_routing_runs_company_counts",
        ),
        CheckConstraint(
            "tier_a_count >= 0 AND tier_b_count >= 0 AND "
            "tier_c_count >= 0 AND tier_d_count >= 0",
            name="ck_prospect_routing_runs_tier_counts",
        ),
        CheckConstraint(
            "routed_companies + blocked_companies = total_companies",
            name="ck_prospect_routing_runs_routed_blocked_sum",
        ),
        CheckConstraint(
            "tier_a_count + tier_b_count + tier_c_count + tier_d_count = routed_companies",
            name="ck_prospect_routing_runs_tier_sum",
        ),
        UniqueConstraint(
            "import_session_id",
            "rules_version",
            "configuration_hash",
            name="uq_prospect_routing_runs_configuration",
        ),
        Index(
            "ix_prospect_routing_runs_session_created",
            "import_session_id",
            "created_at",
        ),
        Index("ix_prospect_routing_runs_status_updated", "status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    import_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_sessions.id", ondelete="CASCADE"), nullable=False
    )
    rules_version: Mapped[str] = mapped_column(String(80), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    criteria_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    weights_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    total_companies: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    routed_companies: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_companies: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tier_a_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tier_b_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tier_c_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tier_d_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProspectRouteModel(Base):
    __tablename__ = "prospect_routes"
    __table_args__ = (
        CheckConstraint("pre_score >= 0 AND pre_score <= 100", name="ck_prospect_routes_score"),
        CheckConstraint(
            "execution_generation > 0",
            name="ck_prospect_routes_execution_generation",
        ),
        CheckConstraint(
            "recommended_tier IS NULL OR recommended_tier IN ('A','B','C','D')",
            name="ck_prospect_routes_recommended_tier",
        ),
        CheckConstraint(
            "effective_tier IS NULL OR effective_tier IN ('A','B','C','D')",
            name="ck_prospect_routes_effective_tier",
        ),
        CheckConstraint(
            "review_status IN ('suggested','confirmed','overridden','blocked')",
            name="ck_prospect_routes_review_status",
        ),
        CheckConstraint("contact_count >= 0", name="ck_prospect_routes_contact_count"),
        CheckConstraint(
            "(review_status = 'blocked' AND recommended_tier IS NULL AND effective_tier IS NULL) "
            "OR (review_status <> 'blocked' AND recommended_tier IS NOT NULL "
            "AND effective_tier IS NOT NULL)",
            name="ck_prospect_routes_blocked_tier",
        ),
        UniqueConstraint(
            "routing_run_id",
            "execution_generation",
            "company_id",
            name="uq_prospect_routes_run_generation_company",
        ),
        Index(
            "ix_prospect_routes_run_generation_tier",
            "routing_run_id",
            "execution_generation",
            "effective_tier",
        ),
        Index(
            "ix_prospect_routes_run_generation_review",
            "routing_run_id",
            "execution_generation",
            "review_status",
        ),
        Index(
            "ix_prospect_routes_run_generation_score",
            "routing_run_id",
            "execution_generation",
            "pre_score",
        ),
        Index(
            "ix_prospect_routes_run_generation_contact",
            "routing_run_id",
            "execution_generation",
            "has_usable_contact",
            "preferred_role_category",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    routing_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("prospect_routing_runs.id", ondelete="CASCADE"), nullable=False
    )
    execution_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    pre_score: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_tier: Mapped[str | None] = mapped_column(String(1))
    effective_tier: Mapped[str | None] = mapped_column(String(1))
    feature_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    warning_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False)
    override_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(String(160))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_usable_contact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_usable_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preferred_role_category: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
