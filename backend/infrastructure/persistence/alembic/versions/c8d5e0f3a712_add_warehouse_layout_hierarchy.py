"""Add normalized, versioned warehouse layout hierarchy."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c8d5e0f3a712"
down_revision = "b7c4d9e2f601"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warehouse_layout_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("warehouse_map_id", sa.Integer(), sa.ForeignKey("warehouse_maps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coordinate_frame_id", sa.Integer(), sa.ForeignKey("warehouse_coordinate_frames.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("warehouse_map_id", "version", name="uq_warehouse_layout_version"),
        sa.CheckConstraint("status IN ('draft', 'locked', 'superseded')", name="ck_warehouse_layout_version_status"),
    )
    op.create_index("ix_warehouse_layout_versions_warehouse_map_id", "warehouse_layout_versions", ["warehouse_map_id"])
    op.create_index("ix_warehouse_layout_versions_coordinate_frame_id", "warehouse_layout_versions", ["coordinate_frame_id"])
    op.create_index("ix_warehouse_layout_versions_status", "warehouse_layout_versions", ["status"])
    op.create_index("uq_warehouse_layout_locked", "warehouse_layout_versions", ["warehouse_map_id"], unique=True, postgresql_where=sa.text("status = 'locked'"))

    op.create_table(
        "warehouse_aisles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("layout_version_id", sa.Integer(), sa.ForeignKey("warehouse_layout_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("geometry_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("layout_version_id", "code", name="uq_warehouse_aisle_code"),
    )
    op.create_index("ix_warehouse_aisles_layout_version_id", "warehouse_aisles", ["layout_version_id"])
    op.create_table(
        "warehouse_racks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("aisle_id", sa.Integer(), sa.ForeignKey("warehouse_aisles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("geometry_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("aisle_id", "code", name="uq_warehouse_rack_code"),
    )
    op.create_index("ix_warehouse_racks_aisle_id", "warehouse_racks", ["aisle_id"])
    op.create_table(
        "warehouse_shelves",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rack_id", sa.Integer(), sa.ForeignKey("warehouse_racks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("geometry_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("rack_id", "level", name="uq_warehouse_shelf_level"),
    )
    op.create_index("ix_warehouse_shelves_rack_id", "warehouse_shelves", ["rack_id"])
    op.create_table(
        "warehouse_bins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shelf_id", sa.Integer(), sa.ForeignKey("warehouse_shelves.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("geometry_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("shelf_id", "code", name="uq_warehouse_bin_code"),
    )
    op.create_index("ix_warehouse_bins_shelf_id", "warehouse_bins", ["shelf_id"])
    op.create_table(
        "warehouse_safety_zones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("layout_version_id", sa.Integer(), sa.ForeignKey("warehouse_layout_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("geometry_json", sa.JSON(), nullable=False),
        sa.Column("min_z_m", sa.Float()),
        sa.Column("max_z_m", sa.Float()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("layout_version_id", "code", name="uq_warehouse_safety_zone_code"),
        sa.CheckConstraint("kind IN ('no_fly', 'keep_out', 'slow', 'landing')", name="ck_warehouse_safety_zone_kind"),
    )
    op.create_index("ix_warehouse_safety_zones_layout_version_id", "warehouse_safety_zones", ["layout_version_id"])
    op.add_column("warehouse_scan_targets", sa.Column("layout_version_id", sa.Integer(), nullable=True))
    op.add_column("warehouse_scan_targets", sa.Column("bin_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_scan_target_layout_version", "warehouse_scan_targets", "warehouse_layout_versions", ["layout_version_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_scan_target_bin", "warehouse_scan_targets", "warehouse_bins", ["bin_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_warehouse_scan_targets_layout_version_id", "warehouse_scan_targets", ["layout_version_id"])
    op.create_index("ix_warehouse_scan_targets_bin_id", "warehouse_scan_targets", ["bin_id"])


def downgrade() -> None:
    op.drop_index("ix_warehouse_scan_targets_bin_id", table_name="warehouse_scan_targets")
    op.drop_index("ix_warehouse_scan_targets_layout_version_id", table_name="warehouse_scan_targets")
    op.drop_constraint("fk_scan_target_bin", "warehouse_scan_targets", type_="foreignkey")
    op.drop_constraint("fk_scan_target_layout_version", "warehouse_scan_targets", type_="foreignkey")
    op.drop_column("warehouse_scan_targets", "bin_id")
    op.drop_column("warehouse_scan_targets", "layout_version_id")
    op.drop_table("warehouse_safety_zones")
    op.drop_table("warehouse_bins")
    op.drop_table("warehouse_shelves")
    op.drop_table("warehouse_racks")
    op.drop_table("warehouse_aisles")
    op.drop_table("warehouse_layout_versions")
