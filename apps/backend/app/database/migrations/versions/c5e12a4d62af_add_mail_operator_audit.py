"""Add stable operator identities and campaign action history.

Revision ID: c5e12a4d62af
Revises: b4e63f0ca102
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5e12a4d62af"
down_revision: str | None = "b4e63f0ca102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mail_campaigns", sa.Column("approved_issuer", sa.Text(), nullable=True))
    op.add_column("mail_campaigns", sa.Column("approved_subject", sa.String(255), nullable=True))
    op.create_check_constraint(
        "ck_mail_campaign_approved_identity", "mail_campaigns",
        "(approved_issuer IS NULL) = (approved_subject IS NULL)",
    )
    op.create_table(
        "mail_campaign_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("actor_name", sa.String(160), nullable=False),
        sa.Column("actor_issuer", sa.Text(), nullable=True),
        sa.Column("actor_subject", sa.String(255), nullable=True),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["mail_campaigns.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "action IN ('create', 'approve', 'pause', 'resume', 'cancel')",
            name="ck_mail_campaign_audit_action",
        ),
        sa.CheckConstraint(
            "(actor_issuer IS NULL) = (actor_subject IS NULL)",
            name="ck_mail_campaign_audit_identity",
        ),
    )
    op.create_index(
        "ix_mail_campaign_audit_page", "mail_campaign_audit",
        ["campaign_id", "occurred_at", "id"],
    )


def downgrade() -> None:
    op.drop_table("mail_campaign_audit")
    op.drop_constraint("ck_mail_campaign_approved_identity", "mail_campaigns", type_="check")
    op.drop_column("mail_campaigns", "approved_subject")
    op.drop_column("mail_campaigns", "approved_issuer")
