"""add persistent prospect batches

Revision ID: d2a1b2c3d4e5
Revises: f8c1d2e3a4b5
Create Date: 2026-07-31 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d2a1b2c3d4e5"
down_revision: str | None = "f8c1d2e3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # D1 was applied to the long-lived development database before its final
    # position/error-code closure landed in the merged migration file. Fresh
    # databases already have these fields from D1, so repair only when absent.
    inspector = sa.inspect(op.get_bind())
    discovery_task_columns = {
        column["name"] for column in inspector.get_columns("discovery_tasks")
    }
    if "error_code" not in discovery_task_columns:
        op.add_column(
            "discovery_tasks",
            sa.Column("error_code", sa.String(length=100), nullable=True),
        )

    candidate_columns = {
        column["name"]
        for column in inspector.get_columns("discovery_task_candidates")
    }
    if "position" not in candidate_columns:
        op.add_column(
            "discovery_task_candidates",
            sa.Column("position", sa.Integer(), nullable=True),
        )
        op.execute(
            sa.text(
                """
                WITH ranked AS (
                    SELECT id,
                           row_number() OVER (
                               PARTITION BY task_id ORDER BY created_at, id
                           ) - 1 AS position
                    FROM discovery_task_candidates
                )
                UPDATE discovery_task_candidates AS candidate
                SET position = ranked.position
                FROM ranked
                WHERE candidate.id = ranked.id
                """
            )
        )
        op.alter_column(
            "discovery_task_candidates",
            "position",
            existing_type=sa.Integer(),
            nullable=False,
        )

    inspector = sa.inspect(op.get_bind())
    candidate_unique_names = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(
            "discovery_task_candidates"
        )
    }
    if "uq_discovery_candidates_task_position" not in candidate_unique_names:
        op.create_unique_constraint(
            "uq_discovery_candidates_task_position",
            "discovery_task_candidates",
            ["task_id", "position"],
        )

    op.create_table(
        "prospect_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("discovery_task_id", sa.Uuid(), nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("effective_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "effective_count > 0 AND effective_count <= 5",
            name="ck_prospect_batches_effective_range",
        ),
        sa.CheckConstraint(
            "effective_count <= requested_count",
            name="ck_prospect_batches_effective_lte_requested",
        ),
        sa.CheckConstraint("requested_count > 0", name="ck_prospect_batches_requested_positive"),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','partial_failed','failed')",
            name="ck_prospect_batches_status",
        ),
        sa.ForeignKeyConstraint(["discovery_task_id"], ["discovery_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_prospect_batches_discovery_task",
        "prospect_batches",
        ["discovery_task_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_prospect_batches_status", "prospect_batches", ["status"], unique=False)

    op.create_table(
        "prospect_batch_companies",
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("pipeline_version", sa.String(length=80), nullable=False),
        sa.Column("current_stage", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("research_id", sa.Uuid(), nullable=True),
        sa.Column("opportunity_id", sa.Uuid(), nullable=True),
        sa.Column("selected_contact_id", sa.Uuid(), nullable=True),
        sa.Column("outreach_id", sa.Uuid(), nullable=True),
        sa.Column("draft_version", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("qualification_decision", sa.String(length=30), nullable=True),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("contact_name", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.Text(), nullable=True),
        sa.Column("contact_source_url", sa.Text(), nullable=True),
        sa.Column("draft_subject", sa.Text(), nullable=True),
        sa.Column("draft_status", sa.String(length=30), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "current_stage IN ('queued','validating','researching','awaiting_evidence_review',"
            "'scoring','discovering_contact','generating_draft','completed','needs_review','failed')",
            name="ck_prospect_batch_companies_stage",
        ),
        sa.CheckConstraint("position >= 0", name="ck_prospect_batch_companies_position"),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','needs_review','failed')",
            name="ck_prospect_batch_companies_status",
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["prospect_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["outreach_id"], ["outreaches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["research_id"], ["research_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["selected_contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("batch_id", "company_id"),
        sa.UniqueConstraint("batch_id", "position", name="uq_prospect_batch_position"),
    )
    op.create_index(
        "ix_prospect_batch_companies_status",
        "prospect_batch_companies",
        ["batch_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_prospect_batch_company_pipeline",
        "prospect_batch_companies",
        ["company_id", "pipeline_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_prospect_batch_company_pipeline", table_name="prospect_batch_companies")
    op.drop_index("ix_prospect_batch_companies_status", table_name="prospect_batch_companies")
    op.drop_table("prospect_batch_companies")
    op.drop_index("ix_prospect_batches_status", table_name="prospect_batches")
    op.drop_index("ix_prospect_batches_discovery_task", table_name="prospect_batches")
    op.drop_table("prospect_batches")
