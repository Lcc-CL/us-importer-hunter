"""add deterministic prospect pre-score routing

Revision ID: d5c1f2e3a4b6
Revises: d5b1e2f3a4b5
Create Date: 2026-08-02 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5c1f2e3a4b6"
down_revision: str | None = "d5b1e2f3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prospect_routing_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_session_id", sa.Uuid(), nullable=False),
        sa.Column("rules_version", sa.String(length=80), nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("entity_state_hash", sa.String(length=64), nullable=False),
        sa.Column("execution_generation", sa.Integer(), nullable=False),
        sa.Column(
            "criteria_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "weights_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("total_companies", sa.Integer(), nullable=False),
        sa.Column("routed_companies", sa.Integer(), nullable=False),
        sa.Column("blocked_companies", sa.Integer(), nullable=False),
        sa.Column("tier_a_count", sa.Integer(), nullable=False),
        sa.Column("tier_b_count", sa.Integer(), nullable=False),
        sa.Column("tier_c_count", sa.Integer(), nullable=False),
        sa.Column("tier_d_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','partial_completed','failed')",
            name="ck_prospect_routing_runs_status",
        ),
        sa.CheckConstraint(
            "execution_generation > 0",
            name="ck_prospect_routing_runs_generation",
        ),
        sa.CheckConstraint(
            "total_companies >= 0 AND routed_companies >= 0 AND blocked_companies >= 0",
            name="ck_prospect_routing_runs_company_counts",
        ),
        sa.CheckConstraint(
            "tier_a_count >= 0 AND tier_b_count >= 0 AND "
            "tier_c_count >= 0 AND tier_d_count >= 0",
            name="ck_prospect_routing_runs_tier_counts",
        ),
        sa.CheckConstraint(
            "routed_companies + blocked_companies = total_companies",
            name="ck_prospect_routing_runs_routed_blocked_sum",
        ),
        sa.CheckConstraint(
            "tier_a_count + tier_b_count + tier_c_count + tier_d_count = routed_companies",
            name="ck_prospect_routing_runs_tier_sum",
        ),
        sa.ForeignKeyConstraint(
            ["import_session_id"], ["import_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_session_id",
            "rules_version",
            "configuration_hash",
            name="uq_prospect_routing_runs_configuration",
        ),
    )
    op.create_index(
        "ix_prospect_routing_runs_session_created",
        "prospect_routing_runs",
        ["import_session_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_prospect_routing_runs_status_updated",
        "prospect_routing_runs",
        ["status", "updated_at"],
        unique=False,
    )

    op.create_table(
        "prospect_routes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("routing_run_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("pre_score", sa.Float(), nullable=False),
        sa.Column("recommended_tier", sa.String(length=1), nullable=True),
        sa.Column("effective_tier", sa.String(length=1), nullable=True),
        sa.Column(
            "feature_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "warning_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=160), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contact_count", sa.Integer(), nullable=False),
        sa.Column("has_usable_contact", sa.Boolean(), nullable=False),
        sa.Column("has_usable_email", sa.Boolean(), nullable=False),
        sa.Column("preferred_role_category", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "pre_score >= 0 AND pre_score <= 100", name="ck_prospect_routes_score"
        ),
        sa.CheckConstraint(
            "recommended_tier IS NULL OR recommended_tier IN ('A','B','C','D')",
            name="ck_prospect_routes_recommended_tier",
        ),
        sa.CheckConstraint(
            "effective_tier IS NULL OR effective_tier IN ('A','B','C','D')",
            name="ck_prospect_routes_effective_tier",
        ),
        sa.CheckConstraint(
            "review_status IN ('suggested','confirmed','overridden','blocked')",
            name="ck_prospect_routes_review_status",
        ),
        sa.CheckConstraint(
            "contact_count >= 0", name="ck_prospect_routes_contact_count"
        ),
        sa.CheckConstraint(
            "(review_status = 'blocked' AND recommended_tier IS NULL AND effective_tier IS NULL) "
            "OR (review_status <> 'blocked' AND recommended_tier IS NOT NULL "
            "AND effective_tier IS NOT NULL)",
            name="ck_prospect_routes_blocked_tier",
        ),
        sa.ForeignKeyConstraint(
            ["routing_run_id"], ["prospect_routing_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "routing_run_id", "company_id", name="uq_prospect_routes_run_company"
        ),
    )
    op.create_index(
        "ix_prospect_routes_run_tier",
        "prospect_routes",
        ["routing_run_id", "effective_tier"],
        unique=False,
    )
    op.create_index(
        "ix_prospect_routes_run_review",
        "prospect_routes",
        ["routing_run_id", "review_status"],
        unique=False,
    )
    op.create_index(
        "ix_prospect_routes_run_score",
        "prospect_routes",
        ["routing_run_id", "pre_score"],
        unique=False,
    )
    op.create_index(
        "ix_prospect_routes_run_contact",
        "prospect_routes",
        ["routing_run_id", "has_usable_contact", "preferred_role_category"],
        unique=False,
    )

    op.add_column(
        "import_processing_jobs",
        sa.Column(
            "job_type",
            sa.String(length=30),
            server_default="entity_resolution",
            nullable=False,
        ),
    )
    op.add_column(
        "import_processing_jobs", sa.Column("routing_run_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "import_processing_jobs_routing_run_id_fkey",
        "import_processing_jobs",
        "prospect_routing_runs",
        ["routing_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_import_processing_jobs_type",
        "import_processing_jobs",
        "job_type IN ('entity_resolution','prospect_routing')",
    )
    op.create_check_constraint(
        "ck_import_processing_jobs_subject",
        "import_processing_jobs",
        "(job_type = 'entity_resolution' AND routing_run_id IS NULL) OR "
        "(job_type = 'prospect_routing' AND routing_run_id IS NOT NULL)",
    )
    op.create_index(
        "ix_import_processing_jobs_routing_run",
        "import_processing_jobs",
        ["routing_run_id", "created_at"],
        unique=False,
    )

    op.drop_constraint(
        "prospect_batches_discovery_task_id_fkey",
        "prospect_batches",
        type_="foreignkey",
    )
    op.alter_column(
        "prospect_batches", "discovery_task_id", existing_type=sa.Uuid(), nullable=True
    )
    op.create_foreign_key(
        "prospect_batches_discovery_task_id_fkey",
        "prospect_batches",
        "discovery_tasks",
        ["discovery_task_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column(
        "prospect_batches", sa.Column("routing_run_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "prospect_batches",
        sa.Column("routing_selection_hash", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "prospect_batches_routing_run_id_fkey",
        "prospect_batches",
        "prospect_routing_runs",
        ["routing_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_prospect_batches_source",
        "prospect_batches",
        "(discovery_task_id IS NOT NULL AND routing_run_id IS NULL "
        "AND routing_selection_hash IS NULL) OR "
        "(discovery_task_id IS NULL AND routing_run_id IS NOT NULL "
        "AND routing_selection_hash IS NOT NULL)",
    )
    op.create_unique_constraint(
        "uq_prospect_batches_routing_selection",
        "prospect_batches",
        ["routing_run_id", "routing_selection_hash"],
    )
    op.create_index(
        "ix_prospect_batches_routing_run",
        "prospect_batches",
        ["routing_run_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM prospect_batches WHERE routing_run_id IS NOT NULL
                ) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade D5c while routing-sourced prospect batches exist';
                END IF;
                IF EXISTS (
                    SELECT 1 FROM import_processing_jobs
                    WHERE job_type = 'prospect_routing'
                ) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade D5c while prospect routing jobs exist';
                END IF;
            END $$
            """
        )
    )

    op.drop_index("ix_prospect_batches_routing_run", table_name="prospect_batches")
    op.drop_constraint(
        "uq_prospect_batches_routing_selection", "prospect_batches", type_="unique"
    )
    op.drop_constraint("ck_prospect_batches_source", "prospect_batches", type_="check")
    op.drop_constraint(
        "prospect_batches_routing_run_id_fkey", "prospect_batches", type_="foreignkey"
    )
    op.drop_column("prospect_batches", "routing_selection_hash")
    op.drop_column("prospect_batches", "routing_run_id")
    op.drop_constraint(
        "prospect_batches_discovery_task_id_fkey",
        "prospect_batches",
        type_="foreignkey",
    )
    op.alter_column(
        "prospect_batches", "discovery_task_id", existing_type=sa.Uuid(), nullable=False
    )
    op.create_foreign_key(
        "prospect_batches_discovery_task_id_fkey",
        "prospect_batches",
        "discovery_tasks",
        ["discovery_task_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_index(
        "ix_import_processing_jobs_routing_run", table_name="import_processing_jobs"
    )
    op.drop_constraint(
        "ck_import_processing_jobs_subject", "import_processing_jobs", type_="check"
    )
    op.drop_constraint(
        "ck_import_processing_jobs_type", "import_processing_jobs", type_="check"
    )
    op.drop_constraint(
        "import_processing_jobs_routing_run_id_fkey",
        "import_processing_jobs",
        type_="foreignkey",
    )
    op.drop_column("import_processing_jobs", "routing_run_id")
    op.drop_column("import_processing_jobs", "job_type")

    op.drop_index("ix_prospect_routes_run_contact", table_name="prospect_routes")
    op.drop_index("ix_prospect_routes_run_score", table_name="prospect_routes")
    op.drop_index("ix_prospect_routes_run_review", table_name="prospect_routes")
    op.drop_index("ix_prospect_routes_run_tier", table_name="prospect_routes")
    op.drop_table("prospect_routes")
    op.drop_index(
        "ix_prospect_routing_runs_status_updated", table_name="prospect_routing_runs"
    )
    op.drop_index(
        "ix_prospect_routing_runs_session_created", table_name="prospect_routing_runs"
    )
    op.drop_table("prospect_routing_runs")
