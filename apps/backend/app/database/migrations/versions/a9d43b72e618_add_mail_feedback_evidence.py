"""Keep the source and occurrence time of verified provider callbacks.

Revision ID: a9d43b72e618
Revises: f8b6e0382af1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9d43b72e618"
down_revision: str | None = "f8b6e0382af1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mail_feedback",
        sa.Column("source", sa.String(40), nullable=False, server_default=sa.text("'legacy'")),
    )
    op.add_column("mail_feedback", sa.Column("message_id", sa.String(256)))
    op.add_column("mail_feedback", sa.Column("occurred_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE mail_feedback SET source = 'one_click' WHERE event_key LIKE 'unsubscribe:%'")
    op.create_index(
        "ix_mail_feedback_timeline", "mail_feedback", ["delivery_id", "received_at", "event_key"],
    )
    op.drop_index("ix_mail_feedback_delivery", table_name="mail_feedback")


def downgrade() -> None:
    op.create_index("ix_mail_feedback_delivery", "mail_feedback", ["delivery_id"])
    op.drop_index("ix_mail_feedback_timeline", table_name="mail_feedback")
    op.drop_column("mail_feedback", "occurred_at")
    op.drop_column("mail_feedback", "message_id")
    op.drop_column("mail_feedback", "source")
