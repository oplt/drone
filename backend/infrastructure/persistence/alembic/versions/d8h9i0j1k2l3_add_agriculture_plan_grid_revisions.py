"""Persist agriculture planner revisions and saved grid routes."""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "d8h9i0j1k2l3"
down_revision: str | Sequence[str] | None = "c7g8h9i0j1k2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agriculture_mission_plans", sa.Column("grid_revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("agriculture_mission_plans", sa.Column("planner_version", sa.String(64), nullable=False, server_default="agriculture-grid.v1"))
    op.create_table(
        "agriculture_mission_plan_revisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("plan_id", sa.String(64), sa.ForeignKey("agriculture_mission_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("planner_version", sa.String(64), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("grid_geojson", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("estimates_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("plan_id", "revision", name="uq_agri_plan_revision"),
    )
    op.create_index("ix_agriculture_mission_plan_revisions_plan_id", "agriculture_mission_plan_revisions", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_agriculture_mission_plan_revisions_plan_id", table_name="agriculture_mission_plan_revisions")
    op.drop_table("agriculture_mission_plan_revisions")
    op.drop_column("agriculture_mission_plans", "planner_version")
    op.drop_column("agriculture_mission_plans", "grid_revision")
