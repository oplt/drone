"""Add versioned warehouse coordinate frames and pin mission data."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7c4d9e2f601"
down_revision = "a4f8c2e91b03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warehouse_coordinate_frames",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "warehouse_map_id",
            sa.Integer(),
            sa.ForeignKey("warehouse_maps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_frame_id", sa.String(64), nullable=False, server_default="warehouse_map"),
        sa.Column("child_frame_id", sa.String(64), nullable=False, server_default="odom"),
        sa.Column("units", sa.String(16), nullable=False, server_default="m"),
        sa.Column("axis_convention", sa.String(16), nullable=False, server_default="ENU"),
        sa.Column("handedness", sa.String(16), nullable=False, server_default="right"),
        sa.Column("transform_json", sa.JSON(), nullable=False),
        sa.Column("covariance_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("confidence", sa.Float()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "warehouse_map_id", "version", name="uq_warehouse_coordinate_frame_version"
        ),
        sa.CheckConstraint("units = 'm'", name="ck_warehouse_coordinate_frame_units"),
        sa.CheckConstraint(
            "axis_convention = 'ENU' AND handedness = 'right'",
            name="ck_warehouse_coordinate_frame_axes",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'locked', 'superseded')",
            name="ck_warehouse_coordinate_frame_status",
        ),
    )
    op.create_index(
        "ix_warehouse_coordinate_frames_warehouse_map_id",
        "warehouse_coordinate_frames",
        ["warehouse_map_id"],
    )
    op.create_index(
        "ix_warehouse_coordinate_frames_status", "warehouse_coordinate_frames", ["status"]
    )
    op.create_index(
        "idx_warehouse_coordinate_frame_map_status",
        "warehouse_coordinate_frames",
        ["warehouse_map_id", "status"],
    )
    op.create_index(
        "uq_warehouse_coordinate_frame_locked",
        "warehouse_coordinate_frames",
        ["warehouse_map_id"],
        unique=True,
        postgresql_where=sa.text("status = 'locked'"),
    )
    op.add_column("warehouse_models", sa.Column("coordinate_frame_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_warehouse_model_coordinate_frame",
        "warehouse_models",
        "warehouse_coordinate_frames",
        ["coordinate_frame_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_warehouse_models_coordinate_frame_id",
        "warehouse_models",
        ["coordinate_frame_id"],
    )
    op.add_column("warehouse_assets", sa.Column("coordinate_frame_id", sa.Integer(), nullable=True))
    op.add_column(
        "warehouse_assets",
        sa.Column("frame_id", sa.String(64), nullable=False, server_default="odom"),
    )
    op.create_foreign_key(
        "fk_warehouse_asset_coordinate_frame",
        "warehouse_assets",
        "warehouse_coordinate_frames",
        ["coordinate_frame_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_warehouse_assets_coordinate_frame_id",
        "warehouse_assets",
        ["coordinate_frame_id"],
    )
    op.add_column(
        "warehouse_scan_targets", sa.Column("coordinate_frame_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_scan_target_coordinate_frame",
        "warehouse_scan_targets",
        "warehouse_coordinate_frames",
        ["coordinate_frame_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_warehouse_scan_targets_coordinate_frame_id",
        "warehouse_scan_targets",
        ["coordinate_frame_id"],
    )
    op.add_column(
        "warehouse_inspection_missions",
        sa.Column("coordinate_frame_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_inspection_mission_coordinate_frame",
        "warehouse_inspection_missions",
        "warehouse_coordinate_frames",
        ["coordinate_frame_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_warehouse_inspection_missions_coordinate_frame_id",
        "warehouse_inspection_missions",
        ["coordinate_frame_id"],
    )
    # Deliberately do not manufacture an identity transform for old data. Existing
    # targets remain unpinned and cannot execute until re-localized/recreated.


def downgrade() -> None:
    op.drop_index("ix_warehouse_assets_coordinate_frame_id", table_name="warehouse_assets")
    op.drop_constraint(
        "fk_warehouse_asset_coordinate_frame", "warehouse_assets", type_="foreignkey"
    )
    op.drop_column("warehouse_assets", "frame_id")
    op.drop_column("warehouse_assets", "coordinate_frame_id")
    op.drop_index("ix_warehouse_models_coordinate_frame_id", table_name="warehouse_models")
    op.drop_constraint(
        "fk_warehouse_model_coordinate_frame", "warehouse_models", type_="foreignkey"
    )
    op.drop_column("warehouse_models", "coordinate_frame_id")
    op.drop_index(
        "ix_warehouse_inspection_missions_coordinate_frame_id",
        table_name="warehouse_inspection_missions",
    )
    op.drop_constraint(
        "fk_inspection_mission_coordinate_frame",
        "warehouse_inspection_missions",
        type_="foreignkey",
    )
    op.drop_column("warehouse_inspection_missions", "coordinate_frame_id")
    op.drop_index(
        "ix_warehouse_scan_targets_coordinate_frame_id", table_name="warehouse_scan_targets"
    )
    op.drop_constraint(
        "fk_scan_target_coordinate_frame", "warehouse_scan_targets", type_="foreignkey"
    )
    op.drop_column("warehouse_scan_targets", "coordinate_frame_id")
    op.drop_table("warehouse_coordinate_frames")
