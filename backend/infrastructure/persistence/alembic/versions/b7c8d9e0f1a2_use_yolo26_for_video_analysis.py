"""use YOLO26 defaults for video analysis

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-05-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7c8d9e0f1a2"
down_revision = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "video_analysis_jobs",
        "model_name",
        existing_type=sa.String(128),
        server_default="yolo26s.pt",
        existing_nullable=False,
    )
    op.execute(
        sa.text(
            "UPDATE video_analysis_jobs "
            "SET model_name = 'yolo26s.pt' "
            "WHERE status = 'queued' AND model_name = 'yolo11n.pt'"
        )
    )


def downgrade() -> None:
    op.alter_column(
        "video_analysis_jobs",
        "model_name",
        existing_type=sa.String(128),
        server_default="yolo11n.pt",
        existing_nullable=False,
    )
