"""link research runs to companies

Adds two columns to research_runs. No other table is touched and no existing
row's data changes.

- company_id: optional link to a canonical company. NULLABLE because research
  also runs on prospects that are not in the database yet, and ON DELETE SET
  NULL so a run survives company deletion as an audit record of what was
  proposed. No unique constraint — a company may be researched many times.
  company_name and website stay as snapshots of what was researched.

- rejected_json: why proposals were refused. Without it, rejection detail
  would live only in the process that produced the run, so a reloaded run
  could not explain itself and GET would degrade to bare warnings.

Hand-edited after autogenerate: `rejected_json` is NOT NULL, and adding a
NOT NULL column to a populated table needs a server default. It is backfilled
with '[]' and the default is then dropped, so new rows must supply the value
from the application rather than silently defaulting.

Revision ID: fc77daaecd96
Revises: 2031082e3176
Create Date: 2026-07-18 22:18:45.977163
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "fc77daaecd96"
down_revision: str | None = "2031082e3176"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("research_runs", sa.Column("company_id", sa.Uuid(), nullable=True))
    op.add_column(
        "research_runs",
        sa.Column(
            "rejected_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("research_runs", "rejected_json", server_default=None)
    op.create_index("ix_research_runs_company_id", "research_runs", ["company_id"], unique=False)
    op.create_foreign_key(
        "fk_research_runs_company",
        "research_runs",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_research_runs_company", "research_runs", type_="foreignkey")
    op.drop_index("ix_research_runs_company_id", table_name="research_runs")
    op.drop_column("research_runs", "rejected_json")
    op.drop_column("research_runs", "company_id")
