"""Add PostGIS indexes for agriculture spatial delivery."""
from collections.abc import Sequence

from alembic import op

revision: str = "f4m5n6o7p8q9"
down_revision: str | Sequence[str] | None = "f3l4m5n6o7p8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep SQLite/local contract tests usable; production uses PostGIS.
    if op.get_bind().dialect.name == "postgresql":
        op.create_index("idx_agri_observations_geometry_gist", "agriculture_observations", ["geometry"], postgresql_using="gist")
        op.create_index("idx_agri_frame_lineage_footprint_gist", "agriculture_frame_lineage", ["footprint"], postgresql_using="gist")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("idx_agri_frame_lineage_footprint_gist", table_name="agriculture_frame_lineage")
        op.drop_index("idx_agri_observations_geometry_gist", table_name="agriculture_observations")
