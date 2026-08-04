"""add Umail export and suppression foundation

Revision ID: d5d2a1b2c3d4
Revises: d5c1f2e3a4b6
Create Date: 2026-08-02 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5d2a1b2c3d4"
down_revision: str | None = "d5c1f2e3a4b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "suppression_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("company", sa.String(length=200), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("deactivated_by", sa.String(length=160), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "num_nonnulls(email, domain, company) = 1",
            name="ck_suppression_entries_single_target",
        ),
        sa.CheckConstraint(
            "(active AND deactivated_by IS NULL AND deactivated_at IS NULL) OR "
            "(NOT active AND deactivated_by IS NOT NULL AND deactivated_at IS NOT NULL)",
            name="ck_suppression_entries_deactivation_audit",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_suppression_entries_active_email",
        "suppression_entries",
        ["active", "email"],
    )
    op.create_index(
        "ix_suppression_entries_active_domain",
        "suppression_entries",
        ["active", "domain"],
    )
    op.create_index(
        "ix_suppression_entries_active_company",
        "suppression_entries",
        ["active", "company"],
    )
    op.create_index(
        "ix_suppression_entries_created", "suppression_entries", ["created_at"]
    )
    op.create_index(
        "uq_suppression_entries_active_email",
        "suppression_entries",
        ["email"],
        unique=True,
        postgresql_where=sa.text("active AND email IS NOT NULL"),
    )
    op.create_index(
        "uq_suppression_entries_active_domain",
        "suppression_entries",
        ["domain"],
        unique=True,
        postgresql_where=sa.text("active AND domain IS NOT NULL"),
    )
    op.create_index(
        "uq_suppression_entries_active_company",
        "suppression_entries",
        ["company"],
        unique=True,
        postgresql_where=sa.text("active AND company IS NOT NULL"),
    )

    op.create_table(
        "umail_export_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("routing_run_id", sa.Uuid(), nullable=False),
        sa.Column("execution_generation", sa.Integer(), nullable=False),
        sa.Column("campaign", sa.String(length=200), nullable=False),
        sa.Column("mapping_version", sa.String(length=80), nullable=False),
        sa.Column("selection_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("ready_count", sa.Integer(), nullable=False),
        sa.Column("suppressed_count", sa.Integer(), nullable=False),
        sa.Column("invalid_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('prepared','downloaded')",
            name="ck_umail_export_batches_status",
        ),
        sa.CheckConstraint(
            "execution_generation > 0", name="ck_umail_export_batches_generation"
        ),
        sa.CheckConstraint(
            "total_rows >= 0 AND ready_count >= 0 AND suppressed_count >= 0 "
            "AND invalid_count >= 0 AND duplicate_count >= 0",
            name="ck_umail_export_batches_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "ready_count + suppressed_count + invalid_count + duplicate_count = total_rows",
            name="ck_umail_export_batches_counts_sum",
        ),
        sa.CheckConstraint(
            "(status = 'prepared' AND downloaded_at IS NULL) OR "
            "(status = 'downloaded' AND downloaded_at IS NOT NULL)",
            name="ck_umail_export_batches_downloaded_at",
        ),
        sa.ForeignKeyConstraint(
            ["routing_run_id"], ["prospect_routing_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "selection_hash", name="uq_umail_export_batches_selection_hash"
        ),
    )
    op.create_index(
        "ix_umail_export_batches_run_generation_created",
        "umail_export_batches",
        ["routing_run_id", "execution_generation", "created_at"],
    )
    op.create_index(
        "ix_umail_export_batches_status_updated",
        "umail_export_batches",
        ["status", "updated_at"],
    )

    op.create_table(
        "umail_export_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("company_website", sa.String(length=2048), nullable=True),
        sa.Column("contact_name", sa.String(length=200), nullable=True),
        sa.Column("first_name", sa.String(length=200), nullable=True),
        sa.Column("last_name", sa.String(length=200), nullable=True),
        sa.Column("contact_title", sa.String(length=200), nullable=True),
        sa.Column("contact_role", sa.String(length=40), nullable=True),
        sa.Column("contact_seniority", sa.String(length=40), nullable=True),
        sa.Column("is_department_contact", sa.Boolean(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=320), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("route", sa.String(length=1), nullable=False),
        sa.Column("route_review_status", sa.String(length=20), nullable=False),
        sa.Column("pre_score", sa.Float(), nullable=False),
        sa.Column(
            "route_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("exclusion_reason", sa.Text(), nullable=True),
        sa.Column("row_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("position > 0", name="ck_umail_export_rows_position"),
        sa.CheckConstraint("route = 'B'", name="ck_umail_export_rows_effective_b"),
        sa.CheckConstraint(
            "route_review_status IN ('confirmed','overridden')",
            name="ck_umail_export_rows_reviewed",
        ),
        sa.CheckConstraint(
            "pre_score >= 0 AND pre_score <= 100", name="ck_umail_export_rows_score"
        ),
        sa.CheckConstraint(
            "status IN ('ready','suppressed','invalid','duplicate')",
            name="ck_umail_export_rows_status",
        ),
        sa.CheckConstraint(
            "(status = 'ready' AND email IS NOT NULL AND exclusion_reason IS NULL) OR "
            "(status <> 'ready' AND exclusion_reason IS NOT NULL)",
            name="ck_umail_export_rows_exclusion_reason",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["umail_export_batches.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_id", "position", name="uq_umail_export_rows_position"
        ),
        sa.UniqueConstraint(
            "batch_id", "row_fingerprint", name="uq_umail_export_rows_fingerprint"
        ),
    )
    op.create_index(
        "ix_umail_export_rows_batch_status",
        "umail_export_rows",
        ["batch_id", "status", "position"],
    )
    op.create_index(
        "ix_umail_export_rows_batch_company",
        "umail_export_rows",
        ["batch_id", "company_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_umail_export_rows_batch_company", table_name="umail_export_rows")
    op.drop_index("ix_umail_export_rows_batch_status", table_name="umail_export_rows")
    op.drop_table("umail_export_rows")
    op.drop_index(
        "ix_umail_export_batches_status_updated", table_name="umail_export_batches"
    )
    op.drop_index(
        "ix_umail_export_batches_run_generation_created",
        table_name="umail_export_batches",
    )
    op.drop_table("umail_export_batches")
    op.drop_index("ix_suppression_entries_created", table_name="suppression_entries")
    op.drop_index(
        "uq_suppression_entries_active_company", table_name="suppression_entries"
    )
    op.drop_index(
        "uq_suppression_entries_active_domain", table_name="suppression_entries"
    )
    op.drop_index(
        "uq_suppression_entries_active_email", table_name="suppression_entries"
    )
    op.drop_index(
        "ix_suppression_entries_active_company", table_name="suppression_entries"
    )
    op.drop_index(
        "ix_suppression_entries_active_domain", table_name="suppression_entries"
    )
    op.drop_index(
        "ix_suppression_entries_active_email", table_name="suppression_entries"
    )
    op.drop_table("suppression_entries")
