"""promotion company link, source position, one promotion per claim

Prepares research_promotions to carry the result of a human review. No other
table is touched and no existing row's data changes.

- company_id becomes a real foreign key to companies.id with ON DELETE SET
  NULL, matching research_runs.company_id. Deleting a company must never
  delete the record of what was proposed and reviewed; it only breaks the
  link. The supporting index already exists from the initial migration.

- company_source_position joins company_signal_position, so a promotion
  records both rows it produced in the Company.

- edited_kind lets a reviewer correct the kind, not only the detail.

- uq_research_promotions_one_per_claim states explicitly that a claim has at
  most one promotion. The primary key (research_id, claim_position) already
  enforced this; the named constraint makes the intent legible and impossible
  to weaken by changing the key alone.

Hand-edited after autogenerate, which omits CHECK constraints on ALTER TABLE:
ck_research_promotions_rejected_never_promoted was added by hand together with
its drop in downgrade. It is the database-level guarantee for the rule that a
rejected claim never produces company data.

Revision ID: ce8f83bb658b
Revises: fc77daaecd96
Create Date: 2026-07-18 22:49:56.934059
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ce8f83bb658b"
down_revision: str | None = "fc77daaecd96"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_promotions", sa.Column("edited_kind", sa.String(length=30), nullable=True)
    )
    op.add_column(
        "research_promotions", sa.Column("company_source_position", sa.Integer(), nullable=True)
    )
    op.create_unique_constraint(
        "uq_research_promotions_one_per_claim",
        "research_promotions",
        ["research_id", "claim_position"],
    )
    op.create_foreign_key(
        "fk_research_promotions_company",
        "research_promotions",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_research_promotions_rejected_never_promoted",
        "research_promotions",
        "(decision = 'rejected' AND company_signal_position IS NULL"
        " AND company_source_position IS NULL) OR decision <> 'rejected'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_research_promotions_rejected_never_promoted",
        "research_promotions",
        type_="check",
    )
    op.drop_constraint(
        "fk_research_promotions_company", "research_promotions", type_="foreignkey"
    )
    op.drop_constraint(
        "uq_research_promotions_one_per_claim", "research_promotions", type_="unique"
    )
    op.drop_column("research_promotions", "company_source_position")
    op.drop_column("research_promotions", "edited_kind")
