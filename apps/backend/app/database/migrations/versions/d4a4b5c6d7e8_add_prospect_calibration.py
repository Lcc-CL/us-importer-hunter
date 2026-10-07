"""add prospect quality calibration

Revision ID: d4a4b5c6d7e8
Revises: d3a3b4c5d6e7
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4a4b5c6d7e8"
down_revision: str | None = "d3a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "prospect_batch_companies",
        sa.Column("contact_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "prospect_batch_companies",
        sa.Column(
            "stage_timings_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "ck_prospect_batch_companies_contact_type",
        "prospect_batch_companies",
        "contact_type IS NULL OR contact_type IN ('personal','department','generic')",
    )

    op.create_table(
        "calibration_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("discovery_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prospect_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("website_fetch_mode", sa.String(length=30), nullable=False),
        sa.Column("research_provider_mode", sa.String(length=30), nullable=False),
        sa.Column("draft_provider_mode", sa.String(length=30), nullable=False),
        sa.Column("contact_source_mode", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sample_count BETWEEN 3 AND 5", name="ck_calibration_sample_range"
        ),
        sa.CheckConstraint(
            "website_fetch_mode IN ('real_http','fixture')",
            name="ck_calibration_website_fetch_mode",
        ),
        sa.CheckConstraint(
            "research_provider_mode IN ('real','deterministic_fake')",
            name="ck_calibration_research_provider_mode",
        ),
        sa.CheckConstraint(
            "draft_provider_mode IN ('real','deterministic_fake')",
            name="ck_calibration_draft_provider_mode",
        ),
        sa.CheckConstraint(
            "contact_source_mode = 'official_website'",
            name="ck_calibration_contact_source_mode",
        ),
        sa.ForeignKeyConstraint(
            ["discovery_task_id"], ["discovery_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["prospect_batch_id"], ["prospect_batches.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prospect_batch_id", name="uq_calibration_prospect_batch"),
    )
    op.create_table(
        "calibration_evaluations",
        sa.Column("calibration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_accuracy", sa.Integer(), nullable=False),
        sa.Column("opportunity_reasonableness", sa.Integer(), nullable=False),
        sa.Column("contact_usability", sa.Integer(), nullable=False),
        sa.Column("draft_personalization", sa.Integer(), nullable=False),
        sa.Column("draft_professionalism", sa.Integer(), nullable=False),
        sa.Column("ready_for_real_outreach", sa.Boolean(), nullable=False),
        sa.Column("reviewer_name", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "research_accuracy BETWEEN 1 AND 5",
            name="ck_calibration_eval_research_range",
        ),
        sa.CheckConstraint(
            "opportunity_reasonableness BETWEEN 1 AND 5",
            name="ck_calibration_eval_opportunity_range",
        ),
        sa.CheckConstraint(
            "contact_usability BETWEEN 1 AND 5",
            name="ck_calibration_eval_contact_range",
        ),
        sa.CheckConstraint(
            "draft_personalization BETWEEN 1 AND 5",
            name="ck_calibration_eval_personalization_range",
        ),
        sa.CheckConstraint(
            "draft_professionalism BETWEEN 1 AND 5",
            name="ck_calibration_eval_professionalism_range",
        ),
        sa.ForeignKeyConstraint(
            ["calibration_id"], ["calibration_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("calibration_id", "company_id"),
    )


def downgrade() -> None:
    op.drop_table("calibration_evaluations")
    op.drop_table("calibration_runs")
    op.drop_constraint(
        "ck_prospect_batch_companies_contact_type",
        "prospect_batch_companies",
        type_="check",
    )
    op.drop_column("prospect_batch_companies", "stage_timings_json")
    op.drop_column("prospect_batch_companies", "contact_type")
