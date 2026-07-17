"""persist email draft approval metadata

Revision ID: 4a91c2e8b730
Revises: d6ef81dfc959
Create Date: 2026-07-16 21:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4a91c2e8b730"
down_revision: str | None = "d6ef81dfc959"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_drafts_status_controlled", "email_drafts", type_="check")
    op.alter_column("email_drafts", "status", new_column_name="approval_status")
    op.add_column(
        "email_drafts",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "email_drafts",
        sa.Column("approved_by_name", sa.String(length=200), nullable=True),
    )
    op.create_check_constraint(
        "ck_drafts_approval_status_controlled",
        "email_drafts",
        "approval_status IN ('generated', 'approved', 'rejected')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_drafts_approval_status_controlled", "email_drafts", type_="check"
    )
    op.drop_column("email_drafts", "approved_by_name")
    op.drop_column("email_drafts", "approved_at")
    op.alter_column("email_drafts", "approval_status", new_column_name="status")
    op.create_check_constraint(
        "ck_drafts_status_controlled",
        "email_drafts",
        "status IN ('generated', 'approved', 'rejected')",
    )
