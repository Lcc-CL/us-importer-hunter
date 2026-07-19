"""persist research output language

Adds research_runs.output_language: the language the extractor wrote its
conclusions in.

Only conclusions. `evidence_snippet` is never translated — it must stay a
verbatim substring of the fetched page so ClaimValidator can verify it, which
is the whole anti-hallucination mechanism (ADR-0025 §6).

NOT NULL with a server default of 'en-US' so rows written before this column
existed keep the language they were actually produced in.

Revision ID: c7e2f4a91b83
Revises: b3d5a1c94e27
Create Date: 2026-07-19 22:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7e2f4a91b83"
down_revision: str | None = "b3d5a1c94e27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_runs",
        sa.Column(
            "output_language",
            sa.String(length=10),
            nullable=False,
            server_default="en-US",
        ),
    )


def downgrade() -> None:
    op.drop_column("research_runs", "output_language")
