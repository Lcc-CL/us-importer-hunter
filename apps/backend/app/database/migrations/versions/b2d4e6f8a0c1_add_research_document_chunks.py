"""add deterministic research document chunks

Revision ID: b2d4e6f8a0c1
Revises: a9f1c2d3e4b5
Create Date: 2026-08-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2d4e6f8a0c1"
down_revision: str | None = "a9f1c2d3e4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column(
            "heading_path",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("chunker_version", sa.String(length=100), nullable=False),
        sa.Column("tokenizer_profile", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "status = 'ready'",
            name="ck_research_document_chunks_status",
        ),
        sa.CheckConstraint(
            "chunk_index >= 0 AND token_count > 0",
            name="ck_research_document_chunks_counts",
        ),
        sa.CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset",
            name="ck_research_document_chunks_offsets",
        ),
        sa.CheckConstraint(
            "length(content) > 0 AND length(content_hash) = 64",
            name="ck_research_document_chunks_content",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "company_id"],
            ["research_documents.id", "research_documents.company_id"],
            name="fk_research_document_chunks_document_company",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "chunker_version",
            "chunk_index",
            name="uq_research_document_chunks_sequence",
        ),
        sa.UniqueConstraint(
            "document_id",
            "chunker_version",
            "start_offset",
            "end_offset",
            name="uq_research_document_chunks_offsets",
        ),
    )
    op.create_index(
        "ix_research_document_chunks_company",
        "research_document_chunks",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_document_chunks_document",
        "research_document_chunks",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_document_chunks_document",
        table_name="research_document_chunks",
    )
    op.drop_index(
        "ix_research_document_chunks_company",
        table_name="research_document_chunks",
    )
    op.drop_table("research_document_chunks")
