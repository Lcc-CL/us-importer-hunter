"""Persist manual decisions for SMTP deliveries with an uncertain outcome.

Revision ID: e7c1f224ae19
Revises: d6cb109f1843
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7c1f224ae19"
down_revision: str | None = "d6cb109f1843"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mail_delivery_reconciliations",
        sa.Column("delivery_id", sa.Uuid(), primary_key=True),
        sa.Column("attempt", sa.Integer(), primary_key=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("provider_reference", sa.String(256), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("actor_name", sa.String(160), nullable=False),
        sa.Column("actor_issuer", sa.Text(), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["delivery_id"], ["mail_deliveries.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "decision IN ('accepted', 'not_submitted')", name="ck_mail_reconciliation_decision",
        ),
        sa.CheckConstraint("attempt > 0", name="ck_mail_reconciliation_attempt"),
    )


def downgrade() -> None:
    op.drop_table("mail_delivery_reconciliations")
