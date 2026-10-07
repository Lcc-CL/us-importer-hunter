"""add offline Umail feedback and engagement events

Revision ID: d5d2b1c2d3e4
Revises: d5d2a1b2c3d4
Create Date: 2026-08-03 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5d2b1c2d3e4"
down_revision: str | None = "d5d2a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "umail_result_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_filename", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("mapping_version", sa.String(length=80), nullable=False),
        sa.Column(
            "mapping_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("input_row_count", sa.Integer(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("unmatched_count", sa.Integer(), nullable=False),
        sa.Column("ambiguous_count", sa.Integer(), nullable=False),
        sa.Column("invalid_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("projected_event_count", sa.Integer(), nullable=False),
        sa.Column("projected_suppression_count", sa.Integer(), nullable=False),
        sa.Column("applied_event_count", sa.Integer(), nullable=False),
        sa.Column("suppression_created_count", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('uploaded','parsed','ready_for_review','applied','partial_applied','failed')",
            name="ck_umail_result_imports_status",
        ),
        sa.CheckConstraint(
            "input_row_count >= 0 AND matched_count >= 0 AND unmatched_count >= 0 "
            "AND ambiguous_count >= 0 AND invalid_count >= 0 AND duplicate_count >= 0 "
            "AND projected_event_count >= 0 AND projected_suppression_count >= 0 "
            "AND applied_event_count >= 0 AND suppression_created_count >= 0",
            name="ck_umail_result_imports_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "matched_count + unmatched_count + ambiguous_count + invalid_count + "
            "duplicate_count = input_row_count",
            name="ck_umail_result_imports_counts_sum",
        ),
        sa.CheckConstraint(
            "projected_event_count = matched_count AND "
            "projected_suppression_count <= projected_event_count",
            name="ck_umail_result_imports_projected_counts",
        ),
        sa.CheckConstraint(
            "(status IN ('applied','partial_applied') AND applied_at IS NOT NULL) OR "
            "(status NOT IN ('applied','partial_applied') AND applied_at IS NULL)",
            name="ck_umail_result_imports_applied_at",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "file_sha256",
            "mapping_version",
            name="uq_umail_result_imports_file_mapping",
        ),
    )
    op.create_index(
        "ix_umail_result_imports_status_created",
        "umail_result_imports",
        ["status", "created_at"],
    )

    op.create_table(
        "umail_result_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("result_import_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("export_batch_id", sa.Uuid(), nullable=True),
        sa.Column("export_row_id", sa.Uuid(), nullable=True),
        sa.Column("normalized_email", sa.String(length=320), nullable=True),
        sa.Column("campaign", sa.String(length=200), nullable=True),
        sa.Column("canonical_event_type", sa.String(length=30), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bounce_type", sa.String(length=80), nullable=True),
        sa.Column("message_id", sa.String(length=500), nullable=True),
        sa.Column("match_status", sa.String(length=20), nullable=False),
        sa.Column("matched_export_row_id", sa.Uuid(), nullable=True),
        sa.Column("match_method", sa.String(length=40), nullable=True),
        sa.Column("error_codes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("row_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("row_number >= 2", name="ck_umail_result_rows_number"),
        sa.CheckConstraint(
            "match_status IN ('matched','unmatched','ambiguous','invalid','duplicate')",
            name="ck_umail_result_rows_match_status",
        ),
        sa.CheckConstraint(
            "canonical_event_type IS NULL OR canonical_event_type IN "
            "('sent','delivered','hard_bounced','soft_bounced','bounce_unknown',"
            "'unsubscribed','complained','replied','opened','clicked')",
            name="ck_umail_result_rows_event_type",
        ),
        sa.CheckConstraint(
            "(match_status = 'matched' AND matched_export_row_id IS NOT NULL "
            "AND match_method IS NOT NULL AND canonical_event_type IS NOT NULL "
            "AND occurred_at IS NOT NULL) OR "
            "(match_status <> 'matched' AND matched_export_row_id IS NULL)",
            name="ck_umail_result_rows_match_audit",
        ),
        sa.ForeignKeyConstraint(
            ["result_import_id"], ["umail_result_imports.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["matched_export_row_id"], ["umail_export_rows.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "result_import_id", "row_number", name="uq_umail_result_rows_import_number"
        ),
        sa.UniqueConstraint(
            "result_import_id",
            "row_fingerprint",
            name="uq_umail_result_rows_import_fingerprint",
        ),
    )
    op.create_index(
        "ix_umail_result_rows_import_match",
        "umail_result_rows",
        ["result_import_id", "match_status", "row_number"],
    )
    op.create_index(
        "ix_umail_result_rows_import_event",
        "umail_result_rows",
        ["result_import_id", "canonical_event_type", "row_number"],
    )
    op.create_index(
        "ix_umail_result_rows_matched_export",
        "umail_result_rows",
        ["matched_export_row_id"],
    )

    op.create_table(
        "contact_engagement_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("result_import_id", sa.Uuid(), nullable=False),
        sa.Column("result_row_id", sa.Uuid(), nullable=False),
        sa.Column("export_batch_id", sa.Uuid(), nullable=False),
        sa.Column("export_row_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("campaign", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("event_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('sent','delivered','hard_bounced','soft_bounced',"
            "'bounce_unknown','unsubscribed','complained','replied','opened','clicked')",
            name="ck_contact_engagement_events_type",
        ),
        sa.ForeignKeyConstraint(
            ["result_import_id"], ["umail_result_imports.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["result_row_id"], ["umail_result_rows.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["export_batch_id"], ["umail_export_batches.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["export_row_id"], ["umail_export_rows.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_fingerprint", name="uq_contact_engagement_events_fingerprint"
        ),
    )
    op.create_index(
        "ix_contact_engagement_events_import_time",
        "contact_engagement_events",
        ["result_import_id", "occurred_at"],
    )
    op.create_index(
        "ix_contact_engagement_events_contact_time",
        "contact_engagement_events",
        ["contact_id", "occurred_at"],
    )
    op.create_index(
        "ix_contact_engagement_events_company_time",
        "contact_engagement_events",
        ["company_id", "occurred_at"],
    )
    op.create_index(
        "ix_contact_engagement_events_campaign_type",
        "contact_engagement_events",
        ["campaign", "event_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_contact_engagement_events_campaign_type",
        table_name="contact_engagement_events",
    )
    op.drop_index(
        "ix_contact_engagement_events_company_time",
        table_name="contact_engagement_events",
    )
    op.drop_index(
        "ix_contact_engagement_events_contact_time",
        table_name="contact_engagement_events",
    )
    op.drop_index(
        "ix_contact_engagement_events_import_time",
        table_name="contact_engagement_events",
    )
    op.drop_table("contact_engagement_events")
    op.drop_index("ix_umail_result_rows_matched_export", table_name="umail_result_rows")
    op.drop_index("ix_umail_result_rows_import_event", table_name="umail_result_rows")
    op.drop_index("ix_umail_result_rows_import_match", table_name="umail_result_rows")
    op.drop_table("umail_result_rows")
    op.drop_index(
        "ix_umail_result_imports_status_created", table_name="umail_result_imports"
    )
    op.drop_table("umail_result_imports")
