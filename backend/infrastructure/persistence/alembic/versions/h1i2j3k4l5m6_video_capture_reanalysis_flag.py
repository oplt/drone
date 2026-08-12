"""Add video capture reanalysis_required flag.

Revision ID: h1i2j3k4l5m6
Revises: g0h1i2j3k4l5
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h1i2j3k4l5m6"
down_revision: str | Sequence[str] | None = "g0h1i2j3k4l5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "video_assets",
        sa.Column(
            "reanalysis_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("video_assets", "reanalysis_required", server_default=None)


def downgrade() -> None:
    op.drop_column("video_assets", "reanalysis_required")
