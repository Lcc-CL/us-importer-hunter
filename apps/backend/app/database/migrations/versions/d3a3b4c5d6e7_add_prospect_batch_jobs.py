"""add prospect batch background jobs

Revision ID: d3a3b4c5d6e7
Revises: d2b2c3d4e5f6
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d3a3b4c5d6e7"
down_revision: str | None = "d2b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prospect_batch_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("business_key", sa.String(length=64), nullable=False),
        sa.Column("request_key_hash", sa.String(length=64), nullable=True),
        sa.Column("sender_name", sa.Text(), nullable=True),
        sa.Column("sender_company", sa.Text(), nullable=True),
        sa.Column("sender_value_proposition", sa.Text(), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=160), nullable=True),
        sa.Column("lease_acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_error_summary", sa.Text(), nullable=True),
        sa.Column("recovery_count", sa.Integer(), nullable=False),
        sa.Column("last_recovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','leased','running','completed','failed','cancelled')",
            name="ck_prospect_batch_jobs_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_prospect_batch_jobs_attempt_count"),
        sa.CheckConstraint("max_attempts > 0", name="ck_prospect_batch_jobs_max_attempts"),
        sa.CheckConstraint("recovery_count >= 0", name="ck_prospect_batch_jobs_recovery_count"),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["prospect_batches.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_prospect_batch_jobs_active_business",
        "prospect_batch_jobs",
        ["business_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending','leased','running')"),
    )
    op.create_index(
        "uq_prospect_batch_jobs_request_key",
        "prospect_batch_jobs",
        ["request_key_hash"],
        unique=True,
        postgresql_where=sa.text("request_key_hash IS NOT NULL"),
    )
    op.create_index(
        "ix_prospect_batch_jobs_claim",
        "prospect_batch_jobs",
        ["status", "available_at", "created_at"],
    )
    op.create_index(
        "ix_prospect_batch_jobs_batch",
        "prospect_batch_jobs",
        ["batch_id", "created_at"],
    )
    op.create_index(
        "ix_prospect_batch_jobs_lease_expiry",
        "prospect_batch_jobs",
        ["lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_prospect_batch_jobs_lease_expiry", table_name="prospect_batch_jobs")
    op.drop_index("ix_prospect_batch_jobs_batch", table_name="prospect_batch_jobs")
    op.drop_index("ix_prospect_batch_jobs_claim", table_name="prospect_batch_jobs")
    op.drop_index("uq_prospect_batch_jobs_request_key", table_name="prospect_batch_jobs")
    op.drop_index("uq_prospect_batch_jobs_active_business", table_name="prospect_batch_jobs")
    op.drop_table("prospect_batch_jobs")
