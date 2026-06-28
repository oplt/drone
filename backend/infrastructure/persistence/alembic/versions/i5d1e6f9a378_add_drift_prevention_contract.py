"""Persist transform freshness and map scale calibration evidence."""

import sqlalchemy as sa
from alembic import op

revision = "i5d1e6f9a378"
down_revision = "h4c0d5e8f267"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "warehouse_coordinate_frames",
        sa.Column("localization_method", sa.String(64), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "warehouse_coordinate_frames",
        sa.Column("transform_timestamp", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE warehouse_coordinate_frames SET transform_timestamp = "
        "COALESCE(locked_at, created_at, CURRENT_TIMESTAMP)"
    )
    op.alter_column("warehouse_coordinate_frames", "transform_timestamp", nullable=False)
    op.add_column(
        "warehouse_coordinate_frames",
        sa.Column("max_age_s", sa.Float(), nullable=False, server_default="300"),
    )
    op.add_column(
        "warehouse_coordinate_frames",
        sa.Column("transform_checksum", sa.String(64), nullable=True),
    )
    op.execute(
        "UPDATE warehouse_coordinate_frames SET transform_checksum = "
        "repeat('0', 64) WHERE transform_checksum IS NULL"
    )
    op.alter_column("warehouse_coordinate_frames", "transform_checksum", nullable=False)

    op.add_column("warehouse_map_setup_versions", sa.Column("map_resolution_m", sa.Float()))
    op.add_column(
        "warehouse_map_setup_versions",
        sa.Column("scale", sa.Float(), nullable=False, server_default="1.0"),
    )
    op.add_column(
        "warehouse_map_setup_versions",
        sa.Column("scale_calibration_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "warehouse_map_setup_versions",
        sa.Column("transform_timestamp", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE warehouse_map_setup_versions SET transform_timestamp = "
        "COALESCE(locked_at, created_at, CURRENT_TIMESTAMP)"
    )
    op.alter_column("warehouse_map_setup_versions", "transform_timestamp", nullable=False)
    op.add_column(
        "warehouse_map_setup_versions",
        sa.Column("max_transform_age_s", sa.Float(), nullable=False, server_default="300"),
    )
    op.add_column(
        "warehouse_map_setup_versions",
        sa.Column("covariance_json", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "warehouse_map_setup_versions",
        sa.Column("localization_method", sa.String(64), nullable=False, server_default="legacy"),
    )
    op.create_check_constraint(
        "ck_warehouse_map_setup_scale", "warehouse_map_setup_versions", "scale = 1.0"
    )
    op.create_check_constraint(
        "ck_warehouse_map_setup_resolution",
        "warehouse_map_setup_versions",
        "map_resolution_m IS NULL OR map_resolution_m > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_warehouse_map_setup_resolution", "warehouse_map_setup_versions", type_="check"
    )
    op.drop_constraint(
        "ck_warehouse_map_setup_scale", "warehouse_map_setup_versions", type_="check"
    )
    for column in (
        "localization_method", "covariance_json", "max_transform_age_s",
        "transform_timestamp", "scale_calibration_json", "scale", "map_resolution_m",
    ):
        op.drop_column("warehouse_map_setup_versions", column)
    for column in ("transform_checksum", "max_age_s", "transform_timestamp", "localization_method"):
        op.drop_column("warehouse_coordinate_frames", column)
