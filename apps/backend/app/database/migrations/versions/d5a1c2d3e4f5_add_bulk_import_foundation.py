"""add bulk import foundation

Revision ID: d5a1c2d3e4f5
Revises: d3a3b4c5d6e7
Create Date: 2026-08-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5a1c2d3e4f5"
down_revision: str | None = "d3a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "mapping_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("encoding", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("accepted_rows", sa.Integer(), nullable=False),
        sa.Column("invalid_rows", sa.Integer(), nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("file_size_bytes > 0", name="ck_import_sessions_file_size_positive"),
        sa.CheckConstraint("total_rows >= 0", name="ck_import_sessions_total_nonnegative"),
        sa.CheckConstraint(
            "accepted_rows >= 0", name="ck_import_sessions_accepted_nonnegative"
        ),
        sa.CheckConstraint("invalid_rows >= 0", name="ck_import_sessions_invalid_nonnegative"),
        sa.CheckConstraint(
            "duplicate_rows >= 0", name="ck_import_sessions_duplicate_nonnegative"
        ),
        sa.CheckConstraint(
            "accepted_rows + invalid_rows + duplicate_rows = total_rows",
            name="ck_import_sessions_counts_sum",
        ),
        sa.CheckConstraint(
            "status IN ('receiving','processing','completed','partial_failed','failed')",
            name="ck_import_sessions_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "file_sha256", name="uq_import_sessions_source_hash"),
    )
    op.create_index(
        "ix_import_sessions_status_created",
        "import_sessions",
        ["status", "created_at"],
        unique=False,
    )
    op.create_table(
        "raw_import_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_session_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "error_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("row_number >= 2", name="ck_raw_import_rows_number"),
        sa.CheckConstraint(
            "status IN ('accepted','invalid','duplicate')",
            name="ck_raw_import_rows_status",
        ),
        sa.ForeignKeyConstraint(
            ["import_session_id"], ["import_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_session_id", "row_number", name="uq_raw_import_rows_session_number"
        ),
    )
    op.create_index(
        "ix_raw_import_rows_session_hash",
        "raw_import_rows",
        ["import_session_id", "row_hash"],
        unique=False,
    )
    op.create_index(
        "ix_raw_import_rows_session_status",
        "raw_import_rows",
        ["import_session_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_raw_import_rows_session_status", table_name="raw_import_rows")
    op.drop_index("ix_raw_import_rows_session_hash", table_name="raw_import_rows")
    op.drop_table("raw_import_rows")
    op.drop_index("ix_import_sessions_status_created", table_name="import_sessions")
    op.drop_table("import_sessions")
