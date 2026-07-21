"""record decision roles on contact fit assessments

A title carries several responsibilities; `department` could only hold one.
These columns record the full classification alongside the judgment that used
it — which taxonomy produced it, by what method, how confident, and why.

Nullable on purpose. Rows written before this migration keep reading through
`department`, and are not back-filled: a stored department cannot say what the
second responsibility was, and inventing one would be worse than leaving the
row visibly coarse.

Recorded rather than recomputed for the same reason `prompt_version` lives on
a draft: once the taxonomy changes, a re-derived classification would silently
rewrite the reasoning behind an assessment that was already acted on.

Revision ID: e51b7c3d84af
Revises: c7e2f4a91b83
Create Date: 2026-07-19 23:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e51b7c3d84af"
down_revision: str | None = "c7e2f4a91b83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contact_fit_assessments",
        sa.Column(
            "roles_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "contact_fit_assessments",
        sa.Column("normalized_title", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "contact_fit_assessments",
        sa.Column("classification_method", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "contact_fit_assessments",
        sa.Column("classification_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "contact_fit_assessments",
        sa.Column(
            "classification_reasons_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "contact_fit_assessments",
        sa.Column("taxonomy_version", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contact_fit_assessments", "taxonomy_version")
    op.drop_column("contact_fit_assessments", "classification_reasons_json")
    op.drop_column("contact_fit_assessments", "classification_confidence")
    op.drop_column("contact_fit_assessments", "classification_method")
    op.drop_column("contact_fit_assessments", "normalized_title")
    op.drop_column("contact_fit_assessments", "roles_json")
