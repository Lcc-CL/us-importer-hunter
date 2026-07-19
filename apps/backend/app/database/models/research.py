"""ResearchRun persistence: the run plus its owned child tables.

Four tables, all new — no existing table is touched (ADR-0025). Child rows use
deterministic composite keys so saves diff instead of duplicating, matching the
Company aggregate's pattern.

Page content is deliberately absent: only URLs, fetch metadata and the short
snippets cited as evidence are stored (ADR-0026 §5).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class ResearchRunModel(Base):
    __tablename__ = "research_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'running', 'completed', 'partial', 'failed')",
            name="ck_research_runs_status_controlled",
        ),
        CheckConstraint(
            "pages_fetched >= 0 AND pages_failed >= 0 "
            "AND claims_extracted >= 0 AND claims_validated >= 0",
            name="ck_research_runs_counters_non_negative",
        ),
        CheckConstraint(
            "claims_validated <= claims_extracted",
            name="ck_research_runs_validated_within_extracted",
        ),
        Index("ix_research_runs_status", "status"),
        Index("ix_research_runs_website", "website"),
        Index("ix_research_runs_company_id", "company_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    # Optional link to a canonical company. Nullable because research also runs
    # on prospects that are not in the database yet, and ON DELETE SET NULL so
    # a run survives company deletion as an audit record of what was proposed.
    # No unique constraint: a company may be researched many times.
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL", name="fk_research_runs_company"),
        nullable=True,
    )
    # company_name and website stay as snapshots of what was researched, even
    # if the company is later renamed or deleted.
    company_name: Mapped[str] = mapped_column(String(200))
    website: Mapped[str] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(20))
    failure_code: Mapped[str | None] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pages_fetched: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)
    claims_extracted: Mapped[int] = mapped_column(Integer, default=0)
    claims_validated: Mapped[int] = mapped_column(Integer, default=0)
    extractor_provider: Mapped[str | None] = mapped_column(String(50))
    extractor_model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    warnings_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # Why proposals were refused. Stored so a reloaded run can explain itself:
    # without this, rejection detail would exist only in the process that
    # produced the run, and GET would degrade to bare warnings.
    rejected_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    pages: Mapped[list["ResearchPageModel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="ResearchPageModel.position"
    )
    claims: Mapped[list["ResearchClaimModel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="ResearchClaimModel.position"
    )
    promotions: Mapped[list["ResearchPromotionModel"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ResearchPromotionModel.claim_position",
    )


class ResearchPageModel(Base):
    __tablename__ = "research_pages"
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_research_pages_position_non_negative"),
        CheckConstraint(
            "content_chars >= 0 AND bytes_read >= 0",
            name="ck_research_pages_counters_non_negative",
        ),
        CheckConstraint(
            "http_status BETWEEN 100 AND 599", name="ck_research_pages_http_status_range"
        ),
    )

    research_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE", name="fk_research_pages_run"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str] = mapped_column(Text)
    http_status: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(100))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_chars: Mapped[int] = mapped_column(Integer)
    bytes_read: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[bool] = mapped_column(default=False)
    discovery_reason: Mapped[str] = mapped_column(String(50))


class ResearchClaimModel(Base):
    __tablename__ = "research_claims"
    __table_args__ = (
        # The claim must cite a page belonging to the same run: a composite FK
        # makes that a database invariant, not merely an application check.
        #
        # DEFERRABLE INITIALLY DEFERRED because the aggregate is written in one
        # flush and SQLAlchemy has no row-level ordering between the pages and
        # claims collections (there is no relationship linking a claim to its
        # page, only the composite key). Deferring moves the check to COMMIT,
        # which keeps the invariant fully enforced while allowing the tree to
        # be inserted in any order.
        ForeignKeyConstraint(
            ["research_id", "source_page_position"],
            ["research_pages.research_id", "research_pages.position"],
            ondelete="CASCADE",
            name="fk_research_claims_source_page",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "kind IN ('import_activity', 'china_dependency', 'shipping_fit', "
            "'cargo_value_potential', 'company_scale', 'growth_signal', "
            "'logistics_complexity', 'pain_point')",
            name="ck_research_claims_kind_controlled",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_research_claims_confidence_range"
        ),
        CheckConstraint("length(trim(detail)) > 0", name="ck_research_claims_detail_not_empty"),
        CheckConstraint(
            "length(trim(evidence_snippet)) > 0",
            name="ck_research_claims_snippet_not_empty",
        ),
        Index("ix_research_claims_kind", "kind"),
    )

    research_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE", name="fk_research_claims_run"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str] = mapped_column(Text)
    evidence_snippet: Mapped[str] = mapped_column(Text)
    source_page_position: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)


class ResearchPromotionModel(Base):
    """The trace from a claim to the company signal a human turned it into."""

    __tablename__ = "research_promotions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["research_id", "claim_position"],
            ["research_claims.research_id", "research_claims.position"],
            ondelete="CASCADE",
            name="fk_research_promotions_claim",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "decision IN ('accepted', 'rejected', 'edited')",
            name="ck_research_promotions_decision_controlled",
        ),
        # edited must carry the edited text; the others must not.
        CheckConstraint(
            "(decision = 'edited' AND edited_detail IS NOT NULL "
            "AND length(trim(edited_detail)) > 0) "
            "OR (decision <> 'edited' AND edited_detail IS NULL)",
            name="ck_research_promotions_edited_detail_consistent",
        ),
        Index("ix_research_promotions_company_id", "company_id"),
        # The primary key (research_id, claim_position) already guarantees at
        # most one promotion per claim; this named constraint states that
        # intent explicitly so it cannot be weakened by accident.
        UniqueConstraint(
            "research_id", "claim_position", name="uq_research_promotions_one_per_claim"
        ),
        CheckConstraint(
            "(decision = 'rejected' AND company_signal_position IS NULL"
            " AND company_source_position IS NULL) OR decision <> 'rejected'",
            name="ck_research_promotions_rejected_never_promoted",
        ),
    )

    research_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE", name="fk_research_promotions_run"),
        primary_key=True,
    )
    claim_position: Mapped[int] = mapped_column(primary_key=True)
    decision: Mapped[str] = mapped_column(String(20))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewer_name: Mapped[str | None] = mapped_column(String(200))
    edited_detail: Mapped[str | None] = mapped_column(Text)
    edited_kind: Mapped[str | None] = mapped_column(String(30))
    # Set when the decision is applied to a company. ON DELETE SET NULL keeps
    # the run as an audit record of what was proposed and reviewed even after
    # the company is deleted — matching research_runs.company_id.
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL", name="fk_research_promotions_company"),
        nullable=True,
    )
    company_source_position: Mapped[int | None] = mapped_column(Integer)
    company_signal_position: Mapped[int | None] = mapped_column(Integer)
