"""add flight_id+timestamp indexes to telemetry and flight_events

Revision ID: d1b112563cfe
Revises: 2ef6a4315fe7
Create Date: 2026-04-07 08:34:23.254637

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2


# revision identifiers, used by Alembic.
revision: str = 'd1b112563cfe'
down_revision: Union[str, Sequence[str], None] = '2ef6a4315fe7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('idx_flight_events_flight_time', 'flight_events', ['flight_id', 'created_at'], unique=False)
    op.create_index('idx_telemetry_flight_time', 'telemetry', ['flight_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_telemetry_flight_time', table_name='telemetry')
    op.drop_index('idx_flight_events_flight_time', table_name='flight_events')
