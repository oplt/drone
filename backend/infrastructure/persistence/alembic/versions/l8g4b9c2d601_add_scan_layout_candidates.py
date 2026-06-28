"""Add scan-to-layout candidates, confidence, and calibration pins.

Revision ID: l8g4b9c2d601
Revises: k7f3a8b1c590
"""

import sqlalchemy as sa
from alembic import op

revision = "l8g4b9c2d601"
down_revision = "k7f3a8b1c590"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("warehouse_scan_artifact_sets", sa.Column("sensor_rig_id", sa.Integer()))
    op.add_column("warehouse_scan_artifact_sets", sa.Column("calibration_hash", sa.String(128)))
    op.create_foreign_key(
        "fk_artifact_set_sensor_rig",
        "warehouse_scan_artifact_sets",
        "warehouse_sensor_rigs",
        ["sensor_rig_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_warehouse_scan_artifact_sets_sensor_rig_id",
        "warehouse_scan_artifact_sets",
        ["sensor_rig_id"],
    )
    for table in (
        "warehouse_layout_versions",
        "warehouse_aisles",
        "warehouse_racks",
        "warehouse_shelves",
        "warehouse_bins",
    ):
        op.add_column(table, sa.Column("confidence", sa.Float()))
    op.create_table(
        "warehouse_layout_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "warehouse_map_id",
            sa.Integer(),
            sa.ForeignKey("warehouse_maps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "layout_version_id",
            sa.Integer(),
            sa.ForeignKey("warehouse_layout_versions.id", ondelete="CASCADE"),
        ),
        sa.Column("entity_kind", sa.String(24), nullable=False),
        sa.Column("identity_key", sa.String(256), nullable=False),
        sa.Column("geometry_json", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="provisional"),
        sa.Column("displacement_m", sa.Float()),
        sa.Column("source_sequence", sa.Integer()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "warehouse_map_id",
            "identity_key",
            "source_sequence",
            name="uq_warehouse_layout_candidate_observation",
        ),
        sa.CheckConstraint(
            "entity_kind IN ('aisle','rack','shelf','bin','zone','inspection_target')",
            name="ck_warehouse_layout_candidate_kind",
        ),
        sa.CheckConstraint(
            "status IN ('provisional','needs_review','accepted','rejected')",
            name="ck_warehouse_layout_candidate_status",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_layout_candidate_confidence"
        ),
    )
    for column in ("warehouse_map_id", "layout_version_id", "entity_kind", "status"):
        op.create_index(
            f"ix_warehouse_layout_candidates_{column}", "warehouse_layout_candidates", [column]
        )


def downgrade() -> None:
    op.drop_table("warehouse_layout_candidates")
    for table in (
        "warehouse_bins",
        "warehouse_shelves",
        "warehouse_racks",
        "warehouse_aisles",
        "warehouse_layout_versions",
    ):
        op.drop_column(table, "confidence")
    op.drop_index(
        "ix_warehouse_scan_artifact_sets_sensor_rig_id", table_name="warehouse_scan_artifact_sets"
    )
    op.drop_constraint(
        "fk_artifact_set_sensor_rig", "warehouse_scan_artifact_sets", type_="foreignkey"
    )
    op.drop_column("warehouse_scan_artifact_sets", "calibration_hash")
    op.drop_column("warehouse_scan_artifact_sets", "sensor_rig_id")
