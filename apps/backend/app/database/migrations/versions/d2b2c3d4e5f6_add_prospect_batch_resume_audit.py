"""add prospect batch evidence-resume audit fields

Revision ID: d2b2c3d4e5f6
Revises: d2a1b2c3d4e5
Create Date: 2026-07-31 22:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2b2c3d4e5f6"
down_revision: str | None = "d2a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "prospect_batch_companies",
        sa.Column(
            "blocking_claim_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "prospect_batch_companies",
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "prospect_batch_companies",
        sa.Column("resumed_from_stage", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "prospect_batch_companies",
        sa.Column("resume_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_prospect_batch_companies_blocking_claim_count",
        "prospect_batch_companies",
        "blocking_claim_count >= 0",
    )
    op.create_check_constraint(
        "ck_prospect_batch_companies_resume_count",
        "prospect_batch_companies",
        "resume_count >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_prospect_batch_companies_resume_count",
        "prospect_batch_companies",
        type_="check",
    )
    op.drop_constraint(
        "ck_prospect_batch_companies_blocking_claim_count",
        "prospect_batch_companies",
        type_="check",
    )
    op.drop_column("prospect_batch_companies", "resume_count")
    op.drop_column("prospect_batch_companies", "resumed_from_stage")
    op.drop_column("prospect_batch_companies", "resumed_at")
    op.drop_column("prospect_batch_companies", "blocking_claim_count")
