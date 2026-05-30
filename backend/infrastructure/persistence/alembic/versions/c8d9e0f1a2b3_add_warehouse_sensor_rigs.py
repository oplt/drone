"""add warehouse sensor rigs

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-05-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warehouse_sensor_rigs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column(
            "org_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("camera_model", sa.String(length=128), nullable=False),
        sa.Column("stereo_baseline_m", sa.Float(), nullable=True),
        sa.Column("intrinsics_url", sa.String(length=2048), nullable=True),
        sa.Column("extrinsics_url", sa.String(length=2048), nullable=True),
        sa.Column("imu_transform_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("firmware_version", sa.String(length=128), nullable=True),
        sa.Column("isaac_ros_version", sa.String(length=128), nullable=True),
        sa.Column(
            "calibration_status",
            sa.String(length=24),
            nullable=False,
            server_default="missing",
        ),
        sa.Column("calibration_hash", sa.String(length=128), nullable=True),
        sa.Column("calibration_meta", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("org_id", "name", name="uq_warehouse_sensor_rig_org_name"),
    )
    op.create_index("idx_warehouse_sensor_rig_owner_id", "warehouse_sensor_rigs", ["owner_id"])
    op.create_index("idx_warehouse_sensor_rig_org_id", "warehouse_sensor_rigs", ["org_id"])
    op.create_index("idx_warehouse_sensor_rig_name", "warehouse_sensor_rigs", ["name"])
    op.create_index(
        "idx_warehouse_sensor_rig_calibration_status",
        "warehouse_sensor_rigs",
        ["calibration_status"],
    )
    op.create_index(
        "idx_warehouse_sensor_rig_calibration_hash",
        "warehouse_sensor_rigs",
        ["calibration_hash"],
    )
    op.create_index("idx_warehouse_sensor_rig_active", "warehouse_sensor_rigs", ["active"])
    op.create_index(
        "idx_warehouse_sensor_rig_org_active",
        "warehouse_sensor_rigs",
        ["org_id", "active"],
    )


def downgrade() -> None:
    op.drop_index("idx_warehouse_sensor_rig_org_active", table_name="warehouse_sensor_rigs")
    op.drop_index("idx_warehouse_sensor_rig_active", table_name="warehouse_sensor_rigs")
    op.drop_index(
        "idx_warehouse_sensor_rig_calibration_hash", table_name="warehouse_sensor_rigs"
    )
    op.drop_index(
        "idx_warehouse_sensor_rig_calibration_status", table_name="warehouse_sensor_rigs"
    )
    op.drop_index("idx_warehouse_sensor_rig_name", table_name="warehouse_sensor_rigs")
    op.drop_index("idx_warehouse_sensor_rig_org_id", table_name="warehouse_sensor_rigs")
    op.drop_index("idx_warehouse_sensor_rig_owner_id", table_name="warehouse_sensor_rigs")
    op.drop_table("warehouse_sensor_rigs")
