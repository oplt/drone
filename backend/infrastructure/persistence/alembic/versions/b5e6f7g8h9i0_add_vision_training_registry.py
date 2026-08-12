"""Add vision training, model registry, and video model selection.

Revision ID: b5e6f7g8h9i0
Revises: a4d5e6f7g8h9
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b5e6f7g8h9i0"
down_revision: str | Sequence[str] | None = "a4d5e6f7g8h9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def upgrade() -> None:
    op.create_table(
        "vision_training_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("vision_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("vision_datasets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("trainer", sa.String(40), nullable=False, server_default="ultralytics"),
        sa.Column("base_model", sa.String(120), nullable=False),
        sa.Column("preset", sa.String(24), nullable=False, server_default="balanced"),
        sa.Column("epochs", sa.Integer(), nullable=False),
        sa.Column("image_size", sa.Integer(), nullable=False),
        sa.Column("batch_size", sa.Integer(), nullable=False),
        sa.Column("device", sa.String(24), nullable=False, server_default="auto"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("current_epoch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("queue_task_id", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        created_at(),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_vision_training_status",
        ),
    )
    op.create_index(
        "ix_vision_training_runs_project_id", "vision_training_runs", ["project_id"]
    )
    op.create_index(
        "ix_vision_training_runs_dataset_id", "vision_training_runs", ["dataset_id"]
    )
    op.create_index(
        "ix_vision_training_runs_created_by_user_id",
        "vision_training_runs",
        ["created_by_user_id"],
    )
    op.create_table(
        "vision_models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("vision_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("crop", sa.String(120), nullable=False),
        sa.Column("task_type", sa.String(40), nullable=False, server_default="detection"),
        created_at(),
        sa.UniqueConstraint("project_id", "name", name="uq_vision_model_project_name"),
    )
    op.create_index("ix_vision_models_org_id", "vision_models", ["org_id"])
    op.create_index("ix_vision_models_project_id", "vision_models", ["project_id"])
    op.create_table(
        "vision_model_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "model_id",
            sa.String(36),
            sa.ForeignKey("vision_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "training_run_id",
            sa.String(36),
            sa.ForeignKey("vision_training_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("vision_datasets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("architecture", sa.String(80), nullable=False),
        sa.Column("weights_uri", sa.Text(), nullable=False),
        sa.Column("classes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "evaluation_artifacts",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="candidate"),
        created_at(),
        sa.UniqueConstraint("model_id", "version", name="uq_vision_model_version"),
        sa.UniqueConstraint("training_run_id", name="uq_vision_model_training_run"),
        sa.CheckConstraint(
            "status IN ('candidate', 'production', 'archived')",
            name="ck_vision_model_version_status",
        ),
    )
    for name, columns in (
        ("ix_vision_model_versions_model_id", ["model_id"]),
        ("ix_vision_model_versions_training_run_id", ["training_run_id"]),
        ("ix_vision_model_versions_dataset_id", ["dataset_id"]),
        ("ix_vision_model_status", ["model_id", "status"]),
    ):
        op.create_index(name, "vision_model_versions", columns)
    op.create_index(
        "uq_vision_one_production_version",
        "vision_model_versions",
        ["model_id"],
        unique=True,
        postgresql_where=sa.text("status = 'production'"),
    )
    op.add_column(
        "video_analysis_jobs", sa.Column("model_version_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "video_analysis_jobs",
        sa.Column("small_object_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_foreign_key(
        "fk_video_analysis_job_model_version",
        "video_analysis_jobs",
        "vision_model_versions",
        ["model_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_video_analysis_jobs_model_version_id",
        "video_analysis_jobs",
        ["model_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_video_analysis_jobs_model_version_id", table_name="video_analysis_jobs")
    op.drop_constraint(
        "fk_video_analysis_job_model_version",
        "video_analysis_jobs",
        type_="foreignkey",
    )
    op.drop_column("video_analysis_jobs", "small_object_mode")
    op.drop_column("video_analysis_jobs", "model_version_id")
    for table in ("vision_model_versions", "vision_models", "vision_training_runs"):
        op.drop_table(table)
