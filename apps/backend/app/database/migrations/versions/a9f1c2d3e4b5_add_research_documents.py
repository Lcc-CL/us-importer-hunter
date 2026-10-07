"""add durable research documents

Revision ID: a9f1c2d3e4b5
Revises: d5d2b1c2d3e4
Create Date: 2026-08-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a9f1c2d3e4b5"
down_revision: str | None = "d5d2b1c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("final_url", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("trust_level", sa.String(length=30), nullable=False),
        sa.Column("cleaner_version", sa.String(length=80), nullable=False),
        sa.Column("supersedes_document_id", sa.Uuid(), nullable=True),
        sa.Column("duplicate_of_document_id", sa.Uuid(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "source_type IN ('homepage','about','products','capabilities','contact','news',"
            "'pdf','trade_evidence_snapshot','website_other')",
            name="ck_research_documents_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('ready','quarantined','superseded')",
            name="ck_research_documents_status",
        ),
        sa.CheckConstraint(
            "trust_level IN ('first_party','authoritative','derived_trusted','unverified')",
            name="ck_research_documents_trust_level",
        ),
        sa.CheckConstraint(
            "length(trim(source_url)) > 0 AND length(trim(canonical_url)) > 0 "
            "AND length(trim(final_url)) > 0",
            name="ck_research_documents_urls_not_empty",
        ),
        sa.CheckConstraint(
            "length(content) > 0 AND length(content) <= 40000",
            name="ck_research_documents_content_size",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_research_documents_hash_length",
        ),
        sa.CheckConstraint(
            "(status = 'superseded' AND is_current = false AND superseded_at IS NOT NULL) OR "
            "(status IN ('ready','quarantined') AND is_current = true "
            "AND superseded_at IS NULL)",
            name="ck_research_documents_lifecycle",
        ),
        sa.CheckConstraint(
            "supersedes_document_id IS NULL OR supersedes_document_id <> id",
            name="ck_research_documents_not_self_superseding",
        ),
        sa.CheckConstraint(
            "duplicate_of_document_id IS NULL OR duplicate_of_document_id <> id",
            name="ck_research_documents_not_self_duplicate",
        ),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["research_runs.id"],
            name="fk_research_documents_research_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_document_id", "company_id"],
            ["research_documents.id", "research_documents.company_id"],
            name="fk_research_documents_supersedes_same_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of_document_id", "company_id"],
            ["research_documents.id", "research_documents.company_id"],
            name="fk_research_documents_duplicate_same_company",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "company_id", name="uq_research_documents_id_company"),
    )
    op.create_index(
        "uq_research_documents_one_current_url",
        "research_documents",
        ["company_id", "canonical_url"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_index(
        "ix_research_documents_company_hash",
        "research_documents",
        ["company_id", "content_hash"],
        unique=False,
    )
    op.create_index(
        "ix_research_documents_research_run",
        "research_documents",
        ["research_run_id"],
        unique=False,
    )
    op.add_column("research_pages", sa.Column("document_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_research_pages_document",
        "research_pages",
        "research_documents",
        ["document_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_research_pages_document", "research_pages", type_="foreignkey")
    op.drop_column("research_pages", "document_id")
    op.drop_index("ix_research_documents_research_run", table_name="research_documents")
    op.drop_index("ix_research_documents_company_hash", table_name="research_documents")
    op.drop_index("uq_research_documents_one_current_url", table_name="research_documents")
    op.drop_table("research_documents")
