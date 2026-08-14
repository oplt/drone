"""Persist immutable video inference execution profiles.

Revision ID: m6n7o8p9q0r1
Revises: l5m6n7o8p9q0
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "m6n7o8p9q0r1"
down_revision: str | Sequence[str] | None = "l5m6n7o8p9q0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "video_analysis_jobs",
        sa.Column(
            "inference_profile",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.alter_column("video_analysis_jobs", "inference_profile", server_default=None)


def downgrade() -> None:
    op.drop_column("video_analysis_jobs", "inference_profile")
