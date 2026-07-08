"""Add layout entity extraction metadata.

Revision ID: q3l9h7m2c608
Revises: p2k8f3g6b145
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "q3l9h7m2c608"
down_revision: Union[str, Sequence[str], None] = "p2k8f3g6b145"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENTITY_TABLES = (
    "warehouse_aisles",
    "warehouse_racks",
    "warehouse_shelves",
    "warehouse_bins",
    "warehouse_safety_zones",
)


def _add_common(table: str) -> None:
    op.add_column(table, sa.Column("template_id", sa.Integer()))
    op.add_column(table, sa.Column("source_artifact_set_id", sa.Integer()))
    op.add_column(
        table,
        sa.Column("confidence_breakdown_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(table, sa.Column("fit_residual_m", sa.Float()))
    op.add_column(table, sa.Column("observed_point_count", sa.Integer()))
    op.add_column(table, sa.Column("coverage_ratio", sa.Float()))
    op.add_column(table, sa.Column("last_verified_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        f"fk_{table}_template_id",
        table,
        "warehouse_rack_templates",
        ["template_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        f"fk_{table}_source_artifact_set_id",
        table,
        "warehouse_scan_artifact_sets",
        ["source_artifact_set_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f(f"ix_{table}_template_id"), table, ["template_id"])
    op.create_index(op.f(f"ix_{table}_source_artifact_set_id"), table, ["source_artifact_set_id"])
    op.alter_column(table, "confidence_breakdown_json", server_default=None)


def upgrade() -> None:
    for table in _ENTITY_TABLES:
        _add_common(table)
    op.add_column(
        "warehouse_racks",
        sa.Column("face_plane_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "warehouse_bins",
        sa.Column("center_local_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "warehouse_bins",
        sa.Column("volume_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.alter_column("warehouse_racks", "face_plane_json", server_default=None)
    op.alter_column("warehouse_bins", "center_local_json", server_default=None)
    op.alter_column("warehouse_bins", "volume_json", server_default=None)


def downgrade() -> None:
    op.drop_column("warehouse_bins", "volume_json")
    op.drop_column("warehouse_bins", "center_local_json")
    op.drop_column("warehouse_racks", "face_plane_json")
    for table in reversed(_ENTITY_TABLES):
        op.drop_index(op.f(f"ix_{table}_source_artifact_set_id"), table_name=table)
        op.drop_index(op.f(f"ix_{table}_template_id"), table_name=table)
        op.drop_constraint(f"fk_{table}_source_artifact_set_id", table, type_="foreignkey")
        op.drop_constraint(f"fk_{table}_template_id", table, type_="foreignkey")
        op.drop_column(table, "last_verified_at")
        op.drop_column(table, "coverage_ratio")
        op.drop_column(table, "observed_point_count")
        op.drop_column(table, "fit_residual_m")
        op.drop_column(table, "confidence_breakdown_json")
        op.drop_column(table, "source_artifact_set_id")
        op.drop_column(table, "template_id")
