"""Strengthen agriculture flight kind, immutable snapshot metadata and lifecycle."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f9i0j1k2l3m4"
down_revision: str | Sequence[str] | None = "e8h9i0j1k2l3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agriculture_flights", sa.Column("flight_kind", sa.String(32), nullable=False, server_default="agriculture_survey"))
    op.add_column("agriculture_flights", sa.Column("profile_snapshot_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("agriculture_flights", sa.Column("profile_snapshot_hash", sa.String(128)))
    op.create_index("ix_agriculture_flights_flight_kind", "agriculture_flights", ["flight_kind"])
    op.create_index("ix_agriculture_flights_profile_snapshot_hash", "agriculture_flights", ["profile_snapshot_hash"])
    op.create_index("idx_agri_flights_field_created", "agriculture_flights", ["field_id", "created_at"])
    op.create_check_constraint("ck_agri_flight_kind", "agriculture_flights", "flight_kind = 'agriculture_survey'")
    op.create_check_constraint("ck_agri_flight_status", "agriculture_flights", "status IN ('planned', 'preflight', 'running', 'captured', 'processing', 'review', 'published', 'archived', 'failed', 'cancelled')")


def downgrade() -> None:
    op.drop_constraint("ck_agri_flight_status", "agriculture_flights", type_="check")
    op.drop_constraint("ck_agri_flight_kind", "agriculture_flights", type_="check")
    op.drop_index("idx_agri_flights_field_created", table_name="agriculture_flights")
    op.drop_index("ix_agriculture_flights_profile_snapshot_hash", table_name="agriculture_flights")
    op.drop_index("ix_agriculture_flights_flight_kind", table_name="agriculture_flights")
    op.drop_column("agriculture_flights", "profile_snapshot_hash")
    op.drop_column("agriculture_flights", "profile_snapshot_version")
    op.drop_column("agriculture_flights", "flight_kind")
