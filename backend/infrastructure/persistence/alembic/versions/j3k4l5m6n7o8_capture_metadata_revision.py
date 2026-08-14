"""Track capture revisions and register dataset image storage objects.

Revision ID: j3k4l5m6n7o8
Revises: i2j3k4l5m6n7
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "j3k4l5m6n7o8"
down_revision: str | Sequence[str] | None = "i2j3k4l5m6n7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "video_assets",
        sa.Column(
            "capture_metadata_revision",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "video_analysis_jobs",
        sa.Column(
            "capture_metadata_revision",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "vision_dataset_images",
        sa.Column("storage_object_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "vision_dataset_images",
        sa.Column("thumbnail_storage_object_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_vision_dataset_images_storage_object_id",
        "vision_dataset_images",
        "vision_storage_objects",
        ["storage_object_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_vision_dataset_images_thumbnail_storage_object_id",
        "vision_dataset_images",
        "vision_storage_objects",
        ["thumbnail_storage_object_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_vision_dataset_images_storage_object_id",
        "vision_dataset_images",
        ["storage_object_id"],
    )
    op.create_index(
        "ix_vision_dataset_images_thumbnail_storage_object_id",
        "vision_dataset_images",
        ["thumbnail_storage_object_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vision_dataset_images_thumbnail_storage_object_id",
        table_name="vision_dataset_images",
    )
    op.drop_index(
        "ix_vision_dataset_images_storage_object_id",
        table_name="vision_dataset_images",
    )
    op.drop_constraint(
        "fk_vision_dataset_images_thumbnail_storage_object_id",
        "vision_dataset_images",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_vision_dataset_images_storage_object_id",
        "vision_dataset_images",
        type_="foreignkey",
    )
    op.drop_column("vision_dataset_images", "thumbnail_storage_object_id")
    op.drop_column("vision_dataset_images", "storage_object_id")
    op.drop_column("video_analysis_jobs", "capture_metadata_revision")
    op.drop_column("video_assets", "capture_metadata_revision")
