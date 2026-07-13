"""Persist source and processing lineage for offline video analysis."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "u7b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "t6a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("video_analysis_jobs", sa.Column("source_checksum", sa.String(64), nullable=True))
    op.add_column(
        "video_analysis_jobs",
        sa.Column("frames_received", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "video_analysis_jobs",
        sa.Column("frames_processed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "video_analysis_jobs",
        sa.Column("frames_dropped", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "video_analysis_jobs",
        sa.Column("frames_failed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "video_analysis_jobs",
        sa.Column("total_inference_latency_ms", sa.Float(), nullable=False, server_default="0"),
    )
    for column in (
        "frames_received",
        "frames_processed",
        "frames_dropped",
        "frames_failed",
        "total_inference_latency_ms",
    ):
        op.alter_column("video_analysis_jobs", column, server_default=None)


def downgrade() -> None:
    op.drop_column("video_analysis_jobs", "total_inference_latency_ms")
    op.drop_column("video_analysis_jobs", "frames_failed")
    op.drop_column("video_analysis_jobs", "frames_dropped")
    op.drop_column("video_analysis_jobs", "frames_processed")
    op.drop_column("video_analysis_jobs", "frames_received")
    op.drop_column("video_analysis_jobs", "source_checksum")
