"""warehouse inspection targets and results

Revision ID: 20260613_warehouse_inspection
Revises: 20260611_property_patrol
Create Date: 2026-06-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260613_warehouse_inspection"
down_revision: str | Sequence[str] | None = "20260611_property_patrol"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "warehouse_scan_targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("warehouse_map_id", sa.Integer(), nullable=False),
        sa.Column("reference_model_id", sa.Integer(), nullable=True),
        sa.Column("dock_station_id", sa.Integer(), nullable=True),
        sa.Column("aisle_code", sa.String(length=64), nullable=False),
        sa.Column("rack_code", sa.String(length=64), nullable=True),
        sa.Column("shelf_level", sa.Integer(), nullable=True),
        sa.Column("bin_code", sa.String(length=64), nullable=True),
        sa.Column("sku", sa.String(length=128), nullable=True),
        sa.Column("barcode", sa.String(length=128), nullable=True),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("target_point_local_json", sa.JSON(), nullable=False),
        sa.Column("scan_pose_local_json", sa.JSON(), nullable=False),
        sa.Column("shelf_normal_local_json", sa.JSON(), nullable=True),
        sa.Column("standoff_m", sa.Float(), nullable=False),
        sa.Column("hover_time_s", sa.Float(), nullable=False),
        sa.Column("scan_timeout_s", sa.Float(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dock_station_id"], ["warehouse_dock_stations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reference_model_id"], ["warehouse_models.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["warehouse_map_id"], ["warehouse_maps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_warehouse_scan_target_location", "warehouse_scan_targets", ["warehouse_map_id", "aisle_code", "rack_code", "bin_code"], unique=False)
    op.create_index("idx_warehouse_scan_target_map_active", "warehouse_scan_targets", ["warehouse_map_id", "active"], unique=False)
    op.create_index(op.f("ix_warehouse_scan_targets_active"), "warehouse_scan_targets", ["active"], unique=False)
    op.create_index(op.f("ix_warehouse_scan_targets_aisle_code"), "warehouse_scan_targets", ["aisle_code"], unique=False)
    op.create_index(op.f("ix_warehouse_scan_targets_barcode"), "warehouse_scan_targets", ["barcode"], unique=False)
    op.create_index(op.f("ix_warehouse_scan_targets_dock_station_id"), "warehouse_scan_targets", ["dock_station_id"], unique=False)
    op.create_index(op.f("ix_warehouse_scan_targets_reference_model_id"), "warehouse_scan_targets", ["reference_model_id"], unique=False)
    op.create_index(op.f("ix_warehouse_scan_targets_sku"), "warehouse_scan_targets", ["sku"], unique=False)
    op.create_index(op.f("ix_warehouse_scan_targets_warehouse_map_id"), "warehouse_scan_targets", ["warehouse_map_id"], unique=False)

    op.create_table(
        "warehouse_inspection_missions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("warehouse_map_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("scan_mode", sa.String(length=32), nullable=False),
        sa.Column("return_to_dock", sa.Boolean(), nullable=False),
        sa.Column("target_ids_json", sa.JSON(), nullable=False),
        sa.Column("plan_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["warehouse_map_id"], ["warehouse_maps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_warehouse_inspection_mission_map_status", "warehouse_inspection_missions", ["warehouse_map_id", "status"], unique=False)
    op.create_index(op.f("ix_warehouse_inspection_missions_status"), "warehouse_inspection_missions", ["status"], unique=False)
    op.create_index(op.f("ix_warehouse_inspection_missions_warehouse_map_id"), "warehouse_inspection_missions", ["warehouse_map_id"], unique=False)

    op.create_table(
        "warehouse_inspection_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mission_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expected_barcode", sa.String(length=128), nullable=True),
        sa.Column("detected_barcode", sa.String(length=128), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("image_asset_id", sa.Integer(), nullable=True),
        sa.Column("video_asset_id", sa.Integer(), nullable=True),
        sa.Column("drone_pose_local_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["image_asset_id"], ["warehouse_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["mission_id"], ["warehouse_inspection_missions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["warehouse_scan_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_asset_id"], ["warehouse_assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_warehouse_inspection_result_mission_target", "warehouse_inspection_results", ["mission_id", "target_id"], unique=False)
    op.create_index(op.f("ix_warehouse_inspection_results_image_asset_id"), "warehouse_inspection_results", ["image_asset_id"], unique=False)
    op.create_index(op.f("ix_warehouse_inspection_results_mission_id"), "warehouse_inspection_results", ["mission_id"], unique=False)
    op.create_index(op.f("ix_warehouse_inspection_results_status"), "warehouse_inspection_results", ["status"], unique=False)
    op.create_index(op.f("ix_warehouse_inspection_results_target_id"), "warehouse_inspection_results", ["target_id"], unique=False)
    op.create_index(op.f("ix_warehouse_inspection_results_video_asset_id"), "warehouse_inspection_results", ["video_asset_id"], unique=False)


def downgrade() -> None:
    op.drop_table("warehouse_inspection_results")
    op.drop_table("warehouse_inspection_missions")
    op.drop_table("warehouse_scan_targets")
