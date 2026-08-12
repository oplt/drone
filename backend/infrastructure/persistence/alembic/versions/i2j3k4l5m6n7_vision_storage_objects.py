"""Register Vision weights as VisionStorageObject rows.

Revision ID: i2j3k4l5m6n7
Revises: h1i2j3k4l5m6
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "i2j3k4l5m6n7"
down_revision: str | Sequence[str] | None = "h1i2j3k4l5m6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vision_storage_objects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("mime", sa.String(length=128), nullable=False),
        sa.Column("owner_type", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="staged"),
        sa.Column(
            "retention_policy",
            sa.String(length=32),
            nullable=False,
            server_default="model_artifact",
        ),
        sa.Column("backend_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('staged', 'final', 'orphan', 'deleted')",
            name="ck_vision_storage_object_state",
        ),
    )
    op.create_index("ix_vision_storage_objects_checksum", "vision_storage_objects", ["checksum"])
    op.create_index(
        "ix_vision_storage_objects_owner_type", "vision_storage_objects", ["owner_type"]
    )
    op.create_index("ix_vision_storage_objects_owner_id", "vision_storage_objects", ["owner_id"])
    op.create_index("ix_vision_storage_objects_state", "vision_storage_objects", ["state"])
    op.add_column(
        "vision_model_versions",
        sa.Column("storage_object_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_vision_model_versions_storage_object_id",
        "vision_model_versions",
        "vision_storage_objects",
        ["storage_object_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_vision_model_versions_storage_object_id",
        "vision_model_versions",
        ["storage_object_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vision_model_versions_storage_object_id",
        table_name="vision_model_versions",
    )
    op.drop_constraint(
        "fk_vision_model_versions_storage_object_id",
        "vision_model_versions",
        type_="foreignkey",
    )
    op.drop_column("vision_model_versions", "storage_object_id")
    op.drop_index("ix_vision_storage_objects_state", table_name="vision_storage_objects")
    op.drop_index("ix_vision_storage_objects_owner_id", table_name="vision_storage_objects")
    op.drop_index("ix_vision_storage_objects_owner_type", table_name="vision_storage_objects")
    op.drop_index("ix_vision_storage_objects_checksum", table_name="vision_storage_objects")
    op.drop_table("vision_storage_objects")
