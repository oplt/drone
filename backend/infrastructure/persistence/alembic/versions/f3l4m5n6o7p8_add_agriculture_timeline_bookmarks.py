"""Persist agriculture synchronized timeline bookmarks and notes."""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "f3l4m5n6o7p8"
down_revision: str | Sequence[str] | None = "f2k3l4m5n6o7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agriculture_timeline_bookmarks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("frame_lineage_id", sa.String(64), sa.ForeignKey("agriculture_frame_lineage.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("flight_id", "frame_lineage_id", "created_by_user_id", name="uq_agri_timeline_bookmark_user_frame"),
    )
    op.create_index("ix_agriculture_timeline_bookmarks_flight_id", "agriculture_timeline_bookmarks", ["flight_id"])
    op.create_index("ix_agriculture_timeline_bookmarks_frame_lineage_id", "agriculture_timeline_bookmarks", ["frame_lineage_id"])
    op.create_index("ix_agriculture_timeline_bookmarks_created_by_user_id", "agriculture_timeline_bookmarks", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_agriculture_timeline_bookmarks_created_by_user_id", table_name="agriculture_timeline_bookmarks")
    op.drop_index("ix_agriculture_timeline_bookmarks_frame_lineage_id", table_name="agriculture_timeline_bookmarks")
    op.drop_index("ix_agriculture_timeline_bookmarks_flight_id", table_name="agriculture_timeline_bookmarks")
    op.drop_table("agriculture_timeline_bookmarks")
