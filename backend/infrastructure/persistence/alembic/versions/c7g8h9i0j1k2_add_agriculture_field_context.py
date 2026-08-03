"""Persist agriculture boundary revisions and exclusion/obstacle zones."""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "c7g8h9i0j1k2"
down_revision: str | Sequence[str] | None = "b6f7g8h9i0j1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("agriculture_field_boundary_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("created_by_user_id", sa.Integer()), sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("boundary_json", sa.JSON(), nullable=False), sa.Column("area_ha", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("field_id", "revision", name="uq_agri_boundary_field_revision"))
    op.create_index("ix_agriculture_field_boundary_revisions_field_id", "agriculture_field_boundary_revisions", ["field_id"])
    op.create_table("agriculture_field_zones",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("created_by_user_id", sa.Integer()), sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("zone_type", sa.String(16), nullable=False), sa.Column("geometry_json", sa.JSON(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False, server_default=""), sa.Column("kind", sa.String(64), nullable=False, server_default="unknown"),
        sa.Column("radius_m", sa.Float()), sa.Column("height_m", sa.Float()), sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("zone_type IN ('exclusion', 'obstacle')", name="ck_agri_zone_type"))
    op.create_index("ix_agriculture_field_zones_field_id", "agriculture_field_zones", ["field_id"])
    op.create_index("idx_agri_zone_field_type", "agriculture_field_zones", ["field_id", "zone_type"])


def downgrade() -> None:
    op.drop_index("idx_agri_zone_field_type", table_name="agriculture_field_zones")
    op.drop_index("ix_agriculture_field_zones_field_id", table_name="agriculture_field_zones")
    op.drop_table("agriculture_field_zones")
    op.drop_index("ix_agriculture_field_boundary_revisions_field_id", table_name="agriculture_field_boundary_revisions")
    op.drop_table("agriculture_field_boundary_revisions")
