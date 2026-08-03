"""Persist ordered agriculture runtime events for replay and recovery."""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "f0j1k2l3m4n5"
down_revision: str | Sequence[str] | None = "e9i0j1k2l3m4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agriculture_runtime_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),
        sa.Column("state", sa.String(32)),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source", sa.String(96), nullable=False, server_default="agriculture.runtime"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("flight_id", "sequence", name="uq_agri_runtime_event_sequence"),
    )
    op.create_index("idx_agri_runtime_event_flight_sequence", "agriculture_runtime_events", ["flight_id", "sequence"])
    op.create_index("ix_agriculture_runtime_events_flight_id", "agriculture_runtime_events", ["flight_id"])
    op.create_index("ix_agriculture_runtime_events_event_type", "agriculture_runtime_events", ["event_type"])
    op.create_index("ix_agriculture_runtime_events_occurred_at", "agriculture_runtime_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_agriculture_runtime_events_occurred_at", table_name="agriculture_runtime_events")
    op.drop_index("ix_agriculture_runtime_events_event_type", table_name="agriculture_runtime_events")
    op.drop_index("ix_agriculture_runtime_events_flight_id", table_name="agriculture_runtime_events")
    op.drop_index("idx_agri_runtime_event_flight_sequence", table_name="agriculture_runtime_events")
    op.drop_table("agriculture_runtime_events")
