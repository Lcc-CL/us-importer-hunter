"""add persistent importer discovery tasks

Revision ID: f8c1d2e3a4b5
Revises: b7f1c84a9d23
Create Date: 2026-07-30 08:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8c1d2e3a4b5"
down_revision: str | None = "b7f1c84a9d23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discovery_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("original_prompt", sa.Text(), nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("effective_count", sa.Integer(), nullable=False),
        sa.Column("parsed_region", sa.String(length=100), nullable=False),
        sa.Column("parsed_category", sa.String(length=100), nullable=False),
        sa.Column("parsed_keywords", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "provider_failure_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "effective_count <= requested_count",
            name="ck_discovery_tasks_effective_lte_requested",
        ),
        sa.CheckConstraint(
            "effective_count > 0", name="ck_discovery_tasks_effective_positive"
        ),
        sa.CheckConstraint(
            "requested_count > 0", name="ck_discovery_tasks_requested_positive"
        ),
        sa.CheckConstraint(
            "provider_failure_count >= 0",
            name="ck_discovery_tasks_provider_failures_nonnegative",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','partial_failed','failed')",
            name="ck_discovery_tasks_status",
        ),
        sa.ForeignKeyConstraint(["id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_discovery_tasks_status", "discovery_tasks", ["status"], unique=False
    )

    op.create_table(
        "discovery_task_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("normalized_domain", sa.String(length=255), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("product_description", sa.Text(), nullable=True),
        sa.Column("import_evidence", sa.Text(), nullable=True),
        sa.Column("raw_metadata_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("duplicate_of_id", sa.Uuid(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name="ck_discovery_candidates_position_nonnegative"
        ),
        sa.CheckConstraint(
            "status IN ('discovered','ingested','duplicate','failed')",
            name="ck_discovery_candidates_status",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["duplicate_of_id"], ["discovery_task_candidates.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["discovery_tasks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id", "position", name="uq_discovery_candidates_task_position"
        ),
    )
    op.create_index(
        "ix_discovery_candidates_domain",
        "discovery_task_candidates",
        ["normalized_domain"],
        unique=False,
    )
    op.create_index(
        "ix_discovery_candidates_task_status",
        "discovery_task_candidates",
        ["task_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_discovery_candidates_task_status", table_name="discovery_task_candidates"
    )
    op.drop_index(
        "ix_discovery_candidates_domain", table_name="discovery_task_candidates"
    )
    op.drop_table("discovery_task_candidates")
    op.drop_index("ix_discovery_tasks_status", table_name="discovery_tasks")
    op.drop_table("discovery_tasks")
