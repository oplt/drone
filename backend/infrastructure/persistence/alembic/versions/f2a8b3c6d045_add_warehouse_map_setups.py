"""Add versioned warehouse origin and boundary setups."""

import sqlalchemy as sa
from alembic import op

revision = "f2a8b3c6d045"
down_revision = "e1f7a2b5c934"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warehouse_map_setup_versions",
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
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("polygon_local_json", sa.JSON(), nullable=False),
        sa.Column("origin_transform_json", sa.JSON(), nullable=False),
        sa.Column("alignment_deg", sa.Float(), nullable=False, server_default="0"),
        sa.Column("alignment_reference", sa.String(24), nullable=False, server_default="aisle"),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("warehouse_map_id", "version", name="uq_warehouse_map_setup_version"),
        sa.CheckConstraint(
            "status IN ('draft', 'locked', 'superseded')", name="ck_warehouse_map_setup_status"
        ),
        sa.CheckConstraint(
            "alignment_reference IN ('north', 'aisle')",
            name="ck_warehouse_map_setup_alignment_reference",
        ),
    )
    op.create_index(
        "ix_warehouse_map_setup_versions_warehouse_map_id",
        "warehouse_map_setup_versions",
        ["warehouse_map_id"],
    )
    op.create_index(
        "ix_warehouse_map_setup_versions_coordinate_frame_id",
        "warehouse_map_setup_versions",
        ["coordinate_frame_id"],
    )
    op.create_index(
        "ix_warehouse_map_setup_versions_status", "warehouse_map_setup_versions", ["status"]
    )
    op.create_index(
        "uq_warehouse_map_setup_locked",
        "warehouse_map_setup_versions",
        ["warehouse_map_id"],
        unique=True,
        postgresql_where=sa.text("status = 'locked'"),
    )


def downgrade() -> None:
    op.drop_table("warehouse_map_setup_versions")
