"""Add immutable extraction input lineage and provenance states."""

import sqlalchemy as sa
from alembic import op

revision = "g3b9c4d7e156"
down_revision = "f2a8b3c6d045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warehouse_scan_artifact_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "warehouse_map_id",
            sa.Integer(),
            sa.ForeignKey("warehouse_maps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "map_model_id",
            sa.Integer(),
            sa.ForeignKey("warehouse_models.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "coordinate_frame_id",
            sa.Integer(),
            sa.ForeignKey("warehouse_coordinate_frames.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("client_flight_id", sa.String(128), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("inputs_json", sa.JSON(), nullable=False),
        sa.Column("extraction_params_json", sa.JSON(), nullable=False),
        sa.Column("algorithm_version", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for column in ("warehouse_map_id", "map_model_id", "coordinate_frame_id", "client_flight_id"):
        op.create_index(
            f"ix_warehouse_scan_artifact_sets_{column}", "warehouse_scan_artifact_sets", [column]
        )
    op.add_column(
        "warehouse_layout_versions", sa.Column("artifact_set_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "warehouse_layout_versions", sa.Column("input_checksum", sa.String(64), nullable=True)
    )
    op.add_column(
        "warehouse_layout_versions", sa.Column("algorithm_version", sa.String(64), nullable=True)
    )
    op.add_column(
        "warehouse_layout_versions",
        sa.Column("provenance_status", sa.String(24), nullable=False, server_default="auto"),
    )
    op.create_foreign_key(
        "fk_layout_artifact_set",
        "warehouse_layout_versions",
        "warehouse_scan_artifact_sets",
        ["artifact_set_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_warehouse_layout_versions_artifact_set_id",
        "warehouse_layout_versions",
        ["artifact_set_id"],
    )
    op.create_index(
        "ix_warehouse_layout_versions_provenance_status",
        "warehouse_layout_versions",
        ["provenance_status"],
    )
    op.create_check_constraint(
        "ck_warehouse_layout_provenance",
        "warehouse_layout_versions",
        "provenance_status IN ('auto', 'manual', 'confirmed')",
    )
    hierarchy_tables = {
        "warehouse_aisles": "ck_warehouse_aisle_provenance",
        "warehouse_racks": "ck_warehouse_rack_provenance",
        "warehouse_shelves": "ck_warehouse_shelf_provenance",
        "warehouse_bins": "ck_warehouse_bin_provenance",
    }
    for table, constraint_name in hierarchy_tables.items():
        op.add_column(
            table,
            sa.Column("provenance_status", sa.String(24), nullable=False, server_default="auto"),
        )
        op.create_check_constraint(
            constraint_name,
            table,
            "provenance_status IN ('auto', 'manual', 'confirmed')",
        )
    op.add_column(
        "warehouse_scan_targets",
        sa.Column("provenance_status", sa.String(24), nullable=False, server_default="manual"),
    )
    op.create_index(
        "ix_warehouse_scan_targets_provenance_status",
        "warehouse_scan_targets",
        ["provenance_status"],
    )
    op.create_check_constraint(
        "ck_warehouse_scan_target_provenance",
        "warehouse_scan_targets",
        "provenance_status IN ('auto', 'manual', 'confirmed')",
    )
    op.execute(
        "UPDATE warehouse_scan_targets SET provenance_status = 'auto' "
        "WHERE reference_model_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_warehouse_scan_target_provenance", "warehouse_scan_targets", type_="check"
    )
    op.drop_index(
        "ix_warehouse_scan_targets_provenance_status", table_name="warehouse_scan_targets"
    )
    op.drop_column("warehouse_scan_targets", "provenance_status")
    hierarchy_tables = {
        "warehouse_bins": "ck_warehouse_bin_provenance",
        "warehouse_shelves": "ck_warehouse_shelf_provenance",
        "warehouse_racks": "ck_warehouse_rack_provenance",
        "warehouse_aisles": "ck_warehouse_aisle_provenance",
    }
    for table, constraint_name in hierarchy_tables.items():
        op.drop_constraint(
            constraint_name,
            table,
            type_="check",
        )
        op.drop_column(table, "provenance_status")
    op.drop_constraint("ck_warehouse_layout_provenance", "warehouse_layout_versions", type_="check")
    op.drop_index(
        "ix_warehouse_layout_versions_provenance_status", table_name="warehouse_layout_versions"
    )
    op.drop_index(
        "ix_warehouse_layout_versions_artifact_set_id", table_name="warehouse_layout_versions"
    )
    op.drop_constraint("fk_layout_artifact_set", "warehouse_layout_versions", type_="foreignkey")
    for column in ("provenance_status", "algorithm_version", "input_checksum", "artifact_set_id"):
        op.drop_column("warehouse_layout_versions", column)
    op.drop_table("warehouse_scan_artifact_sets")
