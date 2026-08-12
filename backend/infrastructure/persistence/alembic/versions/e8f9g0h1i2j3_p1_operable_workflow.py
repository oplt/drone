"""Add P1 operable video workflow contracts.

Revision ID: e8f9g0h1i2j3
Revises: d7e8f9g0h1i2
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8f9g0h1i2j3"
down_revision: str | Sequence[str] | None = "d7e8f9g0h1i2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("video_assets", sa.Column("captured_at", sa.DateTime(timezone=True)))
    op.add_column(
        "video_assets",
        sa.Column(
            "capture_time_source",
            sa.String(24),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column("video_assets", sa.Column("capture_timezone", sa.String(64)))
    op.add_column(
        "video_assets", sa.Column("capture_time_uncertainty_seconds", sa.Float())
    )
    op.add_column(
        "video_assets",
        sa.Column("sync_offset_seconds", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_video_asset_capture_time_source",
        "video_assets",
        "capture_time_source IN "
        "('container', 'mission', 'operator', 'upload_time', 'unknown')",
    )
    op.alter_column("video_assets", "capture_time_source", server_default=None)
    op.alter_column("video_assets", "sync_offset_seconds", server_default=None)

    op.add_column(
        "video_analysis_jobs",
        sa.Column(
            "stage_timings",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.alter_column("video_analysis_jobs", "stage_timings", server_default=None)

    op.create_table(
        "video_storage_objects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("mime", sa.String(128), nullable=False),
        sa.Column("owner_type", sa.String(32), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("retention_policy", sa.String(32), nullable=False),
        sa.Column("backend_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "state IN ('staged', 'final', 'orphan', 'deleted')",
            name="ck_video_storage_object_state",
        ),
    )
    for name, columns in (
        ("ix_video_storage_objects_checksum", ["checksum"]),
        ("ix_video_storage_objects_owner_type", ["owner_type"]),
        ("ix_video_storage_objects_owner_id", ["owner_id"]),
        ("ix_video_storage_objects_state", ["state"]),
    ):
        op.create_index(name, "video_storage_objects", columns)
    op.add_column(
        "video_detections", sa.Column("storage_object_id", sa.String(36), nullable=True)
    )
    op.create_foreign_key(
        "fk_video_detection_storage_object",
        "video_detections",
        "video_storage_objects",
        ["storage_object_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_video_detections_storage_object_id",
        "video_detections",
        ["storage_object_id"],
    )
    op.create_index(
        "ix_video_detections_job_time_id",
        "video_detections",
        ["job_id", "timestamp_seconds", "id"],
    )

    op.add_column(
        "vision_training_runs",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "vision_training_runs", sa.Column("lease_owner", sa.String(128), nullable=True)
    )
    op.add_column(
        "vision_training_runs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "vision_training_runs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "vision_training_runs",
        sa.Column("terminal_reason_code", sa.String(64), nullable=True),
    )
    op.add_column(
        "vision_training_runs",
        sa.Column("terminal_stage", sa.String(64), nullable=True),
    )
    op.create_check_constraint(
        "ck_vision_training_attempt_nonnegative",
        "vision_training_runs",
        "attempt >= 0",
    )
    # Project scope is intentional: one GPU-producing workflow per project,
    # regardless of which immutable dataset snapshot it uses.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id, row_number() OVER (
                    PARTITION BY project_id ORDER BY created_at DESC, id DESC
                ) AS rank
                FROM vision_training_runs
                WHERE status IN ('queued', 'running', 'cancelling')
            )
            UPDATE vision_training_runs
            SET status = 'failed',
                error = 'Superseded while enforcing one active run per project.',
                finished_at = now(),
                terminal_reason_code = 'ACTIVE_RUN_DEDUPLICATED',
                terminal_stage = 'migration'
            FROM ranked
            WHERE vision_training_runs.id = ranked.id AND ranked.rank > 1
            """
        )
    )
    op.create_index(
        "uq_vision_one_active_training_per_project",
        "vision_training_runs",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('queued', 'running', 'cancelling')"
        ),
    )
    op.create_index(
        "ix_vision_training_lease_expires_at",
        "vision_training_runs",
        ["lease_expires_at"],
    )
    op.alter_column("vision_training_runs", "attempt", server_default=None)
    op.add_column(
        "vision_datasets",
        sa.Column(
            "curation_summary",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.alter_column("vision_datasets", "curation_summary", server_default=None)


def downgrade() -> None:
    op.drop_column("vision_datasets", "curation_summary")
    op.drop_index(
        "ix_vision_training_lease_expires_at", table_name="vision_training_runs"
    )
    op.drop_index(
        "uq_vision_one_active_training_per_project", table_name="vision_training_runs"
    )
    op.drop_constraint(
        "ck_vision_training_attempt_nonnegative",
        "vision_training_runs",
        type_="check",
    )
    for column in (
        "terminal_stage",
        "terminal_reason_code",
        "lease_expires_at",
        "heartbeat_at",
        "lease_owner",
        "attempt",
    ):
        op.drop_column("vision_training_runs", column)
    op.drop_index("ix_video_detections_job_time_id", table_name="video_detections")
    op.drop_index(
        "ix_video_detections_storage_object_id", table_name="video_detections"
    )
    op.drop_constraint(
        "fk_video_detection_storage_object", "video_detections", type_="foreignkey"
    )
    op.drop_column("video_detections", "storage_object_id")
    for name in (
        "ix_video_storage_objects_state",
        "ix_video_storage_objects_owner_id",
        "ix_video_storage_objects_owner_type",
        "ix_video_storage_objects_checksum",
    ):
        op.drop_index(name, table_name="video_storage_objects")
    op.drop_table("video_storage_objects")
    op.drop_column("video_analysis_jobs", "stage_timings")
    op.drop_constraint(
        "ck_video_asset_capture_time_source", "video_assets", type_="check"
    )
    for column in (
        "sync_offset_seconds",
        "capture_time_uncertainty_seconds",
        "capture_timezone",
        "capture_time_source",
        "captured_at",
    ):
        op.drop_column("video_assets", column)
