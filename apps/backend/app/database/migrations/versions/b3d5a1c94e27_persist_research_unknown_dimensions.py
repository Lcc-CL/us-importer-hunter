"""persist research unknown dimensions

Adds research_runs.unknown_dimensions_json: the dimensions an extractor found
no reliable evidence for.

Before this column the value lived only in the process that produced the run,
so a reloaded run could not distinguish "we looked and found nothing" from
"this was never considered". Reviewers need that difference — an unknown
dimension is a prompt to research further, never a negative signal, and it is
never read by scoring (ADR-0025).

NOT NULL with a server default of '[]' so existing rows become explicit empty
lists rather than NULL, and no application code has to handle a third state.
Downgrade simply drops the column; nothing else depends on it.

Revision ID: b3d5a1c94e27
Revises: ce8f83bb658b
Create Date: 2026-07-19 14:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3d5a1c94e27"
down_revision: str | None = "ce8f83bb658b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_runs",
        sa.Column(
            "unknown_dimensions_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("research_runs", "unknown_dimensions_json")
