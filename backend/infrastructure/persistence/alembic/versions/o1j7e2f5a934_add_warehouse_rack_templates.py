"""Add warehouse rack/bin templates.

Revision ID: o1j7e2f5a934
Revises: n0i6d1e4f823
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "o1j7e2f5a934"
down_revision: Union[str, Sequence[str], None] = "n0i6d1e4f823"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "warehouse_rack_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "warehouse_map_id",
            sa.Integer(),
            sa.ForeignKey("warehouse_maps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("rack_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("warehouse_map_id", "name", name="uq_warehouse_rack_template_name"),
    )
    op.create_index(
        "idx_warehouse_rack_template_map_active",
        "warehouse_rack_templates",
        ["warehouse_map_id", "active"],
    )
    op.create_index(
        op.f("ix_warehouse_rack_templates_warehouse_map_id"),
        "warehouse_rack_templates",
        ["warehouse_map_id"],
    )
    op.create_index(
        op.f("ix_warehouse_rack_templates_active"),
        "warehouse_rack_templates",
        ["active"],
    )

    op.create_table(
        "warehouse_rack_template_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("warehouse_rack_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("bay_width_m", sa.Float(), nullable=False),
        sa.Column("shelf_heights_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("bin_pitch_m", sa.Float(), nullable=False),
        sa.Column("bin_count", sa.Integer()),
        sa.Column(
            "left_face_naming",
            sa.String(32),
            nullable=False,
            server_default="left_to_right",
        ),
        sa.Column(
            "right_face_naming",
            sa.String(32),
            nullable=False,
            server_default="right_to_left",
        ),
        sa.Column("barcode_scan_side", sa.String(32), nullable=False, server_default="front"),
        sa.Column("preferred_standoff_m", sa.Float(), nullable=False, server_default="1.2"),
        sa.Column("min_scanner_angle_deg", sa.Float(), nullable=False, server_default="20.0"),
        sa.Column("meta_data", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("template_id", "version", name="uq_warehouse_rack_template_version"),
        sa.CheckConstraint(
            "status IN ('draft','active','superseded')",
            name="ck_warehouse_rack_template_version_status",
        ),
        sa.CheckConstraint("bay_width_m > 0", name="ck_warehouse_rack_template_bay_width"),
        sa.CheckConstraint("bin_pitch_m > 0", name="ck_warehouse_rack_template_bin_pitch"),
        sa.CheckConstraint(
            "bin_count IS NULL OR bin_count > 0",
            name="ck_warehouse_rack_template_bin_count",
        ),
    )
    op.create_index(
        op.f("ix_warehouse_rack_template_versions_template_id"),
        "warehouse_rack_template_versions",
        ["template_id"],
    )
    op.create_index(
        op.f("ix_warehouse_rack_template_versions_status"),
        "warehouse_rack_template_versions",
        ["status"],
    )

    op.add_column("warehouse_racks", sa.Column("template_version_id", sa.Integer()))
    op.add_column(
        "warehouse_racks",
        sa.Column(
            "fitted_transform_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "warehouse_racks",
        sa.Column("template_fit_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_foreign_key(
        "fk_warehouse_rack_template_version",
        "warehouse_racks",
        "warehouse_rack_template_versions",
        ["template_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_warehouse_racks_template_version_id"),
        "warehouse_racks",
        ["template_version_id"],
    )
    op.alter_column("warehouse_racks", "fitted_transform_json", server_default=None)
    op.alter_column("warehouse_racks", "template_fit_json", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_warehouse_racks_template_version_id"), table_name="warehouse_racks")
    op.drop_constraint("fk_warehouse_rack_template_version", "warehouse_racks", type_="foreignkey")
    op.drop_column("warehouse_racks", "template_fit_json")
    op.drop_column("warehouse_racks", "fitted_transform_json")
    op.drop_column("warehouse_racks", "template_version_id")
    op.drop_index(
        op.f("ix_warehouse_rack_template_versions_status"),
        table_name="warehouse_rack_template_versions",
    )
    op.drop_index(
        op.f("ix_warehouse_rack_template_versions_template_id"),
        table_name="warehouse_rack_template_versions",
    )
    op.drop_table("warehouse_rack_template_versions")
    op.drop_index(op.f("ix_warehouse_rack_templates_active"), table_name="warehouse_rack_templates")
    op.drop_index(
        op.f("ix_warehouse_rack_templates_warehouse_map_id"),
        table_name="warehouse_rack_templates",
    )
    op.drop_index(
        "idx_warehouse_rack_template_map_active",
        table_name="warehouse_rack_templates",
    )
    op.drop_table("warehouse_rack_templates")
