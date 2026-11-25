"""Add SMTP worker pulses and an index for live-queue diagnostics.

Revision ID: f8b6e0382af1
Revises: e7c1f224ae19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8b6e0382af1"
down_revision: str | None = "e7c1f224ae19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mail_worker_pulses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sender_hash", sa.String(64), nullable=True),
        sa.Column("verified_only", sa.Boolean(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mail_worker_pulses_seen", "mail_worker_pulses", ["seen_at"])
    op.create_index(
        "ix_mail_delivery_ops", "mail_deliveries", ["status", "campaign_id", "available_at"],
        postgresql_where=sa.text("status IN ('pending', 'sending', 'unknown')"),
    )


def downgrade() -> None:
    op.drop_index("ix_mail_delivery_ops", table_name="mail_deliveries")
    op.drop_table("mail_worker_pulses")
