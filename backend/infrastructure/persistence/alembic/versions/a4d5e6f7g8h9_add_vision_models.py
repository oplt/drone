"""Add agricultural vision projects, datasets, and annotations.

Revision ID: a4d5e6f7g8h9
Revises: z3c4d5e6f7a8b, g1j2k3l4m5n6
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4d5e6f7g8h9"
down_revision: str | Sequence[str] | None = ("z3c4d5e6f7a8b", "g1j2k3l4m5n6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "vision_projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("crop", sa.String(120), nullable=False),
        sa.Column("task_type", sa.String(40), nullable=False, server_default="detection"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *timestamps(),
        sa.CheckConstraint(
            "task_type IN ('detection', 'instance_segmentation')",
            name="ck_vision_project_task_type",
        ),
    )
    op.create_index("ix_vision_projects_org_id", "vision_projects", ["org_id"])
    op.create_index(
        "ix_vision_projects_created_by_user_id",
        "vision_projects",
        ["created_by_user_id"],
    )
    op.create_table(
        "vision_classes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("vision_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("class_index", sa.Integer(), nullable=False),
        timestamps()[0],
        sa.UniqueConstraint("project_id", "name", name="uq_vision_class_project_name"),
        sa.UniqueConstraint(
            "project_id", "class_index", name="uq_vision_class_project_index"
        ),
        sa.CheckConstraint("class_index >= 0", name="ck_vision_class_index_nonnegative"),
    )
    op.create_index("ix_vision_classes_project_id", "vision_classes", ["project_id"])
    op.create_table(
        "vision_datasets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("vision_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("image_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("labeled_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reviewed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("train_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("val_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("test_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("manifest_checksum", sa.String(64), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("project_id", "version", name="uq_vision_dataset_version"),
        sa.CheckConstraint("version > 0", name="ck_vision_dataset_version_positive"),
        sa.CheckConstraint("status IN ('draft', 'locked')", name="ck_vision_dataset_status"),
    )
    op.create_index("ix_vision_datasets_project_id", "vision_datasets", ["project_id"])
    op.create_table(
        "vision_dataset_images",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("vision_datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("thumbnail_uri", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="upload"),
        sa.Column("source_group", sa.String(160), nullable=False),
        sa.Column(
            "source_video_id",
            sa.String(36),
            sa.ForeignKey("video_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("mission_id", sa.String(64), nullable=True),
        sa.Column(
            "field_id",
            sa.Integer(),
            sa.ForeignKey("fields.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("frame_index", sa.Integer(), nullable=True),
        sa.Column("timestamp_seconds", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("perceptual_hash", sa.String(64), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("split", sa.String(8), nullable=True),
        sa.Column(
            "annotation_status", sa.String(24), nullable=False, server_default="unlabeled"
        ),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("altitude_m", sa.Float(), nullable=True),
        sa.Column("heading_deg", sa.Float(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        *timestamps(),
        sa.UniqueConstraint("dataset_id", "sha256", name="uq_vision_image_dataset_sha256"),
        sa.CheckConstraint(
            "split IS NULL OR split IN ('train', 'val', 'test')",
            name="ck_vision_image_split",
        ),
        sa.CheckConstraint(
            "annotation_status IN ('unlabeled', 'labeled', 'reviewed')",
            name="ck_vision_image_annotation_status",
        ),
    )
    for name, columns in (
        ("ix_vision_dataset_images_dataset_id", ["dataset_id"]),
        ("ix_vision_dataset_images_source_video_id", ["source_video_id"]),
        ("ix_vision_dataset_images_mission_id", ["mission_id"]),
        ("ix_vision_dataset_images_field_id", ["field_id"]),
        ("ix_vision_image_dataset_split", ["dataset_id", "split"]),
        ("ix_vision_image_dataset_status", ["dataset_id", "annotation_status"]),
        ("ix_vision_image_source_group", ["dataset_id", "source_group"]),
    ):
        op.create_index(name, "vision_dataset_images", columns)
    op.create_table(
        "vision_annotations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "image_id",
            sa.String(36),
            sa.ForeignKey("vision_dataset_images.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "class_id",
            sa.String(36),
            sa.ForeignKey("vision_classes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("annotation_type", sa.String(24), nullable=False, server_default="bbox"),
        sa.Column("x1", sa.Float(), nullable=False),
        sa.Column("y1", sa.Float(), nullable=False),
        sa.Column("x2", sa.Float(), nullable=False),
        sa.Column("y2", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("segmentation", sa.JSON(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *timestamps(),
        sa.CheckConstraint("annotation_type = 'bbox'", name="ck_vision_annotation_type"),
        sa.CheckConstraint(
            "source IN ('manual', 'auto', 'imported')",
            name="ck_vision_annotation_source",
        ),
        sa.CheckConstraint("x1 >= 0 AND x1 < x2", name="ck_vision_annotation_x"),
        sa.CheckConstraint("y1 >= 0 AND y1 < y2", name="ck_vision_annotation_y"),
    )
    op.create_index("ix_vision_annotations_image_id", "vision_annotations", ["image_id"])
    op.create_index("ix_vision_annotations_class_id", "vision_annotations", ["class_id"])


def downgrade() -> None:
    for table in (
        "vision_annotations",
        "vision_dataset_images",
        "vision_datasets",
        "vision_classes",
        "vision_projects",
    ):
        op.drop_table(table)
