"""merge calibration and research migration heads

Revision ID: e4a5b6c7d8f9
Revises: d4a4b5c6d7e8, b2d4e6f8a0c1
Create Date: 2026-10-07
"""

from collections.abc import Sequence

revision: str = "e4a5b6c7d8f9"
down_revision: str | Sequence[str] | None = ("d4a4b5c6d7e8", "b2d4e6f8a0c1")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
