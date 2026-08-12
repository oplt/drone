"""Add reproducible video tracking options.

Revision ID: c6f7g8h9i0j1
Revises: b5e6f7g8h9i0
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6f7g8h9i0j1"
down_revision: str | Sequence[str] | None = "b5e6f7g8h9i0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "video_analysis_jobs",
        sa.Column(
            "tracking_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "video_analysis_jobs",
        sa.Column(
            "tracker_type",
            sa.String(32),
            nullable=False,
            server_default="bytetrack",
        ),
    )
    op.create_check_constraint(
        "ck_video_analysis_tracker_type",
        "video_analysis_jobs",
        "tracker_type IN ('bytetrack')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_video_analysis_tracker_type", "video_analysis_jobs", type_="check"
    )
    op.drop_column("video_analysis_jobs", "tracker_type")
    op.drop_column("video_analysis_jobs", "tracking_enabled")
