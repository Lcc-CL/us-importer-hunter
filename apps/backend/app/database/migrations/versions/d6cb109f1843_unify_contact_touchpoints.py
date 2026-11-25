"""Unify SMTP delivery reservations and Umail export and feedback history.

Revision ID: d6cb109f1843
Revises: c5e12a4d62af
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d6cb109f1843"
down_revision: str | None = "c5e12a4d62af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contact_touches",
        sa.Column("channel", sa.String(8), primary_key=True),
        sa.Column("source_id", sa.Uuid(), primary_key=True),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("channel IN ('smtp', 'umail')", name="ck_contact_touch_channel"),
        sa.CheckConstraint(
            "(state = 'reserved' AND reserved_at IS NOT NULL AND confirmed_at IS NULL) OR "
            "(state = 'confirmed' AND confirmed_at IS NOT NULL) OR "
            "(channel = 'smtp' AND state IN ('unknown', 'released') "
            "AND reserved_at IS NOT NULL AND confirmed_at IS NULL)",
            name="ck_contact_touch_state",
        ),
    )
    # Older SMTP acceptances without a timed callback get a conservative contact
    # timestamp at migration. Known callbacks retain their original evidence time.
    op.execute("""
        INSERT INTO contact_touches
            (channel, source_id, recipient, state, reserved_at, confirmed_at)
        SELECT 'smtp', delivery.id, lower(btrim(delivery.recipient)),
               CASE WHEN delivery.status = 'accepted' OR events.latest IS NOT NULL THEN 'confirmed'
                    WHEN delivery.status IN ('failed', 'pending', 'suppressed') THEN 'released'
                    WHEN delivery.status = 'unknown' THEN 'unknown'
                    ELSE 'reserved' END,
               CASE WHEN delivery.status = 'accepted' OR events.latest IS NOT NULL
                    THEN NULL ELSE least(delivery.available_at, now()) END,
               CASE WHEN delivery.status = 'accepted' OR events.latest IS NOT NULL
                    THEN COALESCE(events.latest, now()) ELSE NULL END
        FROM mail_deliveries AS delivery
        LEFT JOIN (
            SELECT delivery_id, max(least(received_at, now())) AS latest FROM mail_feedback
            WHERE kind <> 'unsubscribed' GROUP BY delivery_id
        ) AS events ON events.delivery_id = delivery.id
        WHERE delivery.attempt > 0
    """)
    op.execute("""
        INSERT INTO contact_touches
            (channel, source_id, recipient, state, reserved_at, confirmed_at)
        SELECT 'umail', row.id, lower(btrim(row.email)),
               CASE WHEN events.latest IS NOT NULL THEN 'confirmed' ELSE 'reserved' END,
               batch.downloaded_at, events.latest
        FROM umail_export_rows AS row
        JOIN umail_export_batches AS batch ON batch.id = row.batch_id
        LEFT JOIN (
            SELECT export_row_id, max(least(occurred_at, now())) AS latest
            FROM contact_engagement_events GROUP BY export_row_id
        ) AS events ON events.export_row_id = row.id
        WHERE row.status = 'ready' AND row.email IS NOT NULL
            AND (batch.downloaded_at IS NOT NULL OR events.latest IS NOT NULL)
    """)
    op.create_index("ix_contact_touches_recipient", "contact_touches", ["recipient"])


def downgrade() -> None:
    op.drop_table("contact_touches")
