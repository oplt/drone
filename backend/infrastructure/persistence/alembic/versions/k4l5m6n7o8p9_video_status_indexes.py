"""Index video asset/job status for reconcile hot paths.

Revision ID: k4l5m6n7o8p9
Revises: j3k4l5m6n7o8
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k4l5m6n7o8p9"
down_revision: str | Sequence[str] | None = "j3k4l5m6n7o8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_video_assets_status", "video_assets", ["status"], unique=False)
    op.create_index(
        "ix_video_analysis_jobs_status",
        "video_analysis_jobs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_video_analysis_jobs_status_lease",
        "video_analysis_jobs",
        ["status", "lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_video_analysis_jobs_status_lease", table_name="video_analysis_jobs")
    op.drop_index("ix_video_analysis_jobs_status", table_name="video_analysis_jobs")
    op.drop_index("ix_video_assets_status", table_name="video_assets")
