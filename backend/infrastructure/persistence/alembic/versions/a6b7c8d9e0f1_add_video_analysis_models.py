"""add video analysis models

Revision ID: a6b7c8d9e0f1
Revises: f2c3d4e5a6b7
Create Date: 2026-05-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a6b7c8d9e0f1"
down_revision = "f2c3d4e5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(64), nullable=True),
        sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="SET NULL")),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column(
            "uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("fps", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="uploaded"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_video_assets_mission_id", "video_assets", ["mission_id"])
    op.create_index("ix_video_assets_field_id", "video_assets", ["field_id"])
    op.create_index("ix_video_assets_org_id", "video_assets", ["org_id"])
    op.create_index("ix_video_assets_uploaded_by_user_id", "video_assets", ["uploaded_by_user_id"])

    op.create_table(
        "video_analysis_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "video_id",
            sa.String(36),
            sa.ForeignKey("video_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mission_id", sa.String(64), nullable=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(128), nullable=False, server_default="yolo11n.pt"),
        sa.Column("frame_stride_seconds", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("confidence_threshold", sa.Float(), nullable=False, server_default="0.35"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_video_analysis_jobs_video_id", "video_analysis_jobs", ["video_id"])
    op.create_index("ix_video_analysis_jobs_mission_id", "video_analysis_jobs", ["mission_id"])
    op.create_index("ix_video_analysis_jobs_org_id", "video_analysis_jobs", ["org_id"])
    op.create_index("idx_video_analysis_jobs_status", "video_analysis_jobs", ["status"])

    op.create_table(
        "video_detections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("video_analysis_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "video_id",
            sa.String(36),
            sa.ForeignKey("video_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mission_id", sa.String(64), nullable=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("timestamp_seconds", sa.Float(), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("x1", sa.Float(), nullable=False),
        sa.Column("y1", sa.Float(), nullable=False),
        sa.Column("x2", sa.Float(), nullable=False),
        sa.Column("y2", sa.Float(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("altitude_m", sa.Float(), nullable=True),
        sa.Column("heading_deg", sa.Float(), nullable=True),
        sa.Column("evidence_path", sa.Text(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_video_detections_job_id", "video_detections", ["job_id"])
    op.create_index("ix_video_detections_video_id", "video_detections", ["video_id"])
    op.create_index("ix_video_detections_mission_id", "video_detections", ["mission_id"])
    op.create_index("ix_video_detections_org_id", "video_detections", ["org_id"])
    op.create_index(
        "ix_video_detections_job_time", "video_detections", ["job_id", "timestamp_seconds"]
    )
    op.create_index(
        "ix_video_detections_mission_label", "video_detections", ["mission_id", "label"]
    )


def downgrade() -> None:
    op.drop_table("video_detections")
    op.drop_table("video_analysis_jobs")
    op.drop_table("video_assets")
