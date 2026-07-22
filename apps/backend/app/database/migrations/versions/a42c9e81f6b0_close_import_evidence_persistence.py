"""close import evidence quality and aggregate persistence

Revision ID: a42c9e81f6b0
Revises: 0d4c02e927a7
Create Date: 2026-07-21 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a42c9e81f6b0"
down_revision: str | None = "0d4c02e927a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_evidence_quality_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("normalized_shipment_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("total_score", sa.Float(), nullable=False),
        sa.Column("source_reliability_score", sa.Float(), nullable=False),
        sa.Column("entity_resolution_score", sa.Float(), nullable=False),
        sa.Column("identity_completeness_score", sa.Float(), nullable=False),
        sa.Column("cross_source_consistency_score", sa.Float(), nullable=False),
        sa.Column("freshness_score", sa.Float(), nullable=False),
        sa.Column(
            "penalties_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "hard_blockers_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "reasons_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('VERIFIED','USABLE','REVIEW','REJECTED')",
            name="ck_import_quality_status",
        ),
        sa.CheckConstraint(
            "total_score BETWEEN 0 AND 100",
            name="ck_import_quality_total",
        ),
        sa.CheckConstraint(
            "source_reliability_score BETWEEN 0 AND 100 "
            "AND entity_resolution_score BETWEEN 0 AND 100 "
            "AND identity_completeness_score BETWEEN 0 AND 100 "
            "AND cross_source_consistency_score BETWEEN 0 AND 100 "
            "AND freshness_score BETWEEN 0 AND 100",
            name="ck_import_quality_dimensions",
        ),
        sa.ForeignKeyConstraint(
            ["normalized_shipment_id"],
            ["normalized_shipments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalized_shipment_id",
            "input_fingerprint",
            name="uq_import_quality_shipment_fingerprint",
        ),
    )
    op.create_index(
        "uq_import_quality_current_shipment",
        "import_evidence_quality_assessments",
        ["normalized_shipment_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "importer_evidence_aggregates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("importer_identity", sa.String(length=300), nullable=False),
        sa.Column("aggregate_version", sa.String(length=64), nullable=False),
        sa.Column("rule_version", sa.String(length=64), nullable=False),
        sa.Column("aggregate_status", sa.String(length=30), nullable=False),
        sa.Column("promotable", sa.Boolean(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("previous_window_days", sa.Integer(), nullable=False),
        sa.Column(
            "metrics_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "quality_summary_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "blocking_reasons_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status_reasons_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("source_provider_count", sa.Integer(), nullable=False),
        sa.Column("trusted_shipment_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "aggregate_status IN ('READY','PARTIAL','INSUFFICIENT_DATA','BLOCKED')",
            name="ck_importer_aggregate_status",
        ),
        sa.CheckConstraint("window_days > 0", name="ck_importer_aggregate_window"),
        sa.CheckConstraint(
            "previous_window_days > 0",
            name="ck_importer_aggregate_previous_window",
        ),
        sa.CheckConstraint(
            "NOT promotable OR company_id IS NOT NULL",
            name="ck_importer_aggregate_promotable_company",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "importer_identity",
            "window_days",
            "as_of_date",
            "input_fingerprint",
            name="uq_importer_aggregate_input",
        ),
    )
    op.create_index(
        "ix_importer_aggregates_company",
        "importer_evidence_aggregates",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "uq_importer_aggregate_current",
        "importer_evidence_aggregates",
        ["importer_identity", "window_days"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "importer_evidence_aggregate_shipments",
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("normalized_shipment_id", sa.Uuid(), nullable=False),
        sa.Column("quality_assessment_id", sa.Uuid(), nullable=True),
        sa.Column("shipment_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("inclusion_status", sa.String(length=20), nullable=False),
        sa.Column("inclusion_reason", sa.Text(), nullable=False),
        sa.Column("source_provider_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "inclusion_status IN ('trusted','review','rejected','undated','skipped')",
            name="ck_importer_aggregate_inclusion_status",
        ),
        sa.CheckConstraint(
            "source_provider_count >= 0",
            name="ck_importer_aggregate_source_count",
        ),
        sa.ForeignKeyConstraint(
            ["aggregate_id"],
            ["importer_evidence_aggregates.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["normalized_shipment_id"],
            ["normalized_shipments.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["quality_assessment_id"],
            ["import_evidence_quality_assessments.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("aggregate_id", "normalized_shipment_id"),
        sa.UniqueConstraint(
            "aggregate_id",
            "shipment_fingerprint",
            name="uq_importer_aggregate_business_shipment",
        ),
    )


def downgrade() -> None:
    op.drop_table("importer_evidence_aggregate_shipments")
    op.drop_index(
        "uq_importer_aggregate_current",
        table_name="importer_evidence_aggregates",
    )
    op.drop_index(
        "ix_importer_aggregates_company",
        table_name="importer_evidence_aggregates",
    )
    op.drop_table("importer_evidence_aggregates")
    op.drop_index(
        "uq_import_quality_current_shipment",
        table_name="import_evidence_quality_assessments",
    )
    op.drop_table("import_evidence_quality_assessments")
