"""import evidence signal promotion ledger and active projection

Revision ID: b7f1c84a9d23
Revises: a42c9e81f6b0
Create Date: 2026-07-21 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7f1c84a9d23"
down_revision: str | None = "a42c9e81f6b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS = (
    "'import_activity','china_dependency','shipping_fit','cargo_value_potential',"
    "'company_scale','growth_signal','contactability','logistics_complexity'"
)


def upgrade() -> None:
    op.create_table(
        "import_evidence_signal_promotions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("signal_kind", sa.String(length=40), nullable=False),
        sa.Column("signal_detail", sa.Text(), nullable=False),
        sa.Column("normalized_value_json", postgresql.JSONB(), nullable=False),
        sa.Column("source_summary_json", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("quality_status", sa.String(length=20), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("promotion_version", sa.String(length=64), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("promoted_signal_id", sa.Uuid(), nullable=True),
        sa.Column("superseded_by_id", sa.Uuid(), nullable=True),
        sa.Column("rejection_reasons_json", postgresql.JSONB(), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"signal_kind IN ({_KINDS})", name="ck_import_promotion_signal_kind"
        ),
        sa.CheckConstraint(
            "status IN ('CANDIDATE','PROMOTED','SKIPPED','BLOCKED','SUPERSEDED','FAILED')",
            name="ck_import_promotion_status",
        ),
        sa.CheckConstraint(
            "quality_status IS NULL OR quality_status IN "
            "('VERIFIED','USABLE','REVIEW','REJECTED')",
            name="ck_import_promotion_quality_status",
        ),
        sa.CheckConstraint(
            "quality_score IS NULL OR quality_score BETWEEN 0 AND 100",
            name="ck_import_promotion_quality_score",
        ),
        sa.CheckConstraint(
            "length(trim(input_fingerprint)) > 0",
            name="ck_import_promotion_fingerprint_not_empty",
        ),
        sa.ForeignKeyConstraint(
            ["aggregate_id"], ["importer_evidence_aggregates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"],
            ["import_evidence_signal_promotions.id"],
            ondelete="SET NULL",
            name="fk_import_promotion_superseded_by",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "aggregate_id",
            "signal_kind",
            "input_fingerprint",
            name="uq_import_promotion_input",
        ),
    )
    op.create_index(
        "ix_import_promotions_aggregate",
        "import_evidence_signal_promotions",
        ["aggregate_id"],
    )
    op.create_index(
        "uq_import_promotion_current_company_kind",
        "import_evidence_signal_promotions",
        ["company_id", "signal_kind"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "import_evidence_company_signals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("promotion_id", sa.Uuid(), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("signal_kind", sa.String(length=40), nullable=False),
        sa.Column("signal_detail", sa.Text(), nullable=False),
        sa.Column("normalized_value_json", postgresql.JSONB(), nullable=False),
        sa.Column("provenance_json", postgresql.JSONB(), nullable=False),
        sa.Column("quality_status", sa.String(length=20), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("ownership", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("superseded_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"signal_kind IN ({_KINDS})", name="ck_import_projection_signal_kind"
        ),
        sa.CheckConstraint(
            "quality_status IN ('VERIFIED','USABLE')",
            name="ck_import_projection_quality_status",
        ),
        sa.CheckConstraint(
            "quality_score BETWEEN 0 AND 100",
            name="ck_import_projection_quality_score",
        ),
        sa.CheckConstraint(
            "ownership = 'import_evidence'", name="ck_import_projection_ownership"
        ),
        sa.ForeignKeyConstraint(
            ["promotion_id"],
            ["import_evidence_signal_promotions.id"],
            ondelete="CASCADE",
            name="fk_import_projection_promotion",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["aggregate_id"], ["importer_evidence_aggregates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"],
            ["import_evidence_company_signals.id"],
            ondelete="SET NULL",
            name="fk_import_projection_superseded_by",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("promotion_id", name="uq_import_projection_promotion"),
    )
    op.create_index(
        "uq_import_projection_active_company_kind",
        "import_evidence_company_signals",
        ["company_id", "signal_kind"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_foreign_key(
        "fk_import_promotion_signal",
        "import_evidence_signal_promotions",
        "import_evidence_company_signals",
        ["promoted_signal_id"],
        ["id"],
        ondelete="SET NULL",
        deferrable=True,
        initially="DEFERRED",
    )

    op.create_table(
        "import_evidence_promotion_quality_assessments",
        sa.Column("promotion_id", sa.Uuid(), nullable=False),
        sa.Column("quality_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["promotion_id"],
            ["import_evidence_signal_promotions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["quality_assessment_id"],
            ["import_evidence_quality_assessments.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("promotion_id", "quality_assessment_id"),
    )


def downgrade() -> None:
    op.drop_table("import_evidence_promotion_quality_assessments")
    op.drop_constraint(
        "fk_import_promotion_signal",
        "import_evidence_signal_promotions",
        type_="foreignkey",
    )
    op.drop_index(
        "uq_import_projection_active_company_kind",
        table_name="import_evidence_company_signals",
    )
    op.drop_table("import_evidence_company_signals")
    op.drop_index(
        "uq_import_promotion_current_company_kind",
        table_name="import_evidence_signal_promotions",
    )
    op.drop_index(
        "ix_import_promotions_aggregate",
        table_name="import_evidence_signal_promotions",
    )
    op.drop_table("import_evidence_signal_promotions")
