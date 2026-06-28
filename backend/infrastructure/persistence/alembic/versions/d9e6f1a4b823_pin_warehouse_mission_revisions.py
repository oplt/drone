"""Pin warehouse inspection missions to immutable input revisions."""

import sqlalchemy as sa
from alembic import op

revision = "d9e6f1a4b823"
down_revision = "c8d5e0f3a712"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "warehouse_layout_versions", sa.Column("map_model_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_layout_map_model",
        "warehouse_layout_versions",
        "warehouse_models",
        ["map_model_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_warehouse_layout_versions_map_model_id", "warehouse_layout_versions", ["map_model_id"]
    )
    op.create_table(
        "warehouse_inspection_validation_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "warehouse_map_id",
            sa.Integer(),
            sa.ForeignKey("warehouse_maps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "coordinate_frame_id",
            sa.Integer(),
            sa.ForeignKey("warehouse_coordinate_frames.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "layout_version_id",
            sa.Integer(),
            sa.ForeignKey("warehouse_layout_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "map_model_id",
            sa.Integer(),
            sa.ForeignKey("warehouse_models.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("input_checksum", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('passed', 'failed')", name="ck_warehouse_inspection_validation_status"
        ),
    )
    for column in ("warehouse_map_id", "coordinate_frame_id", "layout_version_id", "map_model_id"):
        op.create_index(
            f"ix_warehouse_inspection_validation_results_{column}",
            "warehouse_inspection_validation_results",
            [column],
        )
    op.add_column(
        "warehouse_inspection_missions", sa.Column("layout_version_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "warehouse_inspection_missions", sa.Column("map_model_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "warehouse_inspection_missions",
        sa.Column("validation_result_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "warehouse_inspection_missions",
        sa.Column("artifact_checksums_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    for column, table in (
        ("layout_version_id", "warehouse_layout_versions"),
        ("map_model_id", "warehouse_models"),
        ("validation_result_id", "warehouse_inspection_validation_results"),
    ):
        op.create_foreign_key(
            f"fk_inspection_mission_{column}",
            "warehouse_inspection_missions",
            table,
            [column],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(
            f"ix_warehouse_inspection_missions_{column}", "warehouse_inspection_missions", [column]
        )


def downgrade() -> None:
    for column in ("validation_result_id", "map_model_id", "layout_version_id"):
        op.drop_index(
            f"ix_warehouse_inspection_missions_{column}", table_name="warehouse_inspection_missions"
        )
        op.drop_constraint(
            f"fk_inspection_mission_{column}", "warehouse_inspection_missions", type_="foreignkey"
        )
        op.drop_column("warehouse_inspection_missions", column)
    op.drop_column("warehouse_inspection_missions", "artifact_checksums_json")
    op.drop_table("warehouse_inspection_validation_results")
    op.drop_index(
        "ix_warehouse_layout_versions_map_model_id", table_name="warehouse_layout_versions"
    )
    op.drop_constraint("fk_layout_map_model", "warehouse_layout_versions", type_="foreignkey")
    op.drop_column("warehouse_layout_versions", "map_model_id")
