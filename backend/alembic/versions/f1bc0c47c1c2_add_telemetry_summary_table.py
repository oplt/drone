"""add telemetry_summary table

Revision ID: f1bc0c47c1c2
Revises: df109cbaef54
Create Date: 2026-04-07 08:56:55.679368

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2


# revision identifiers, used by Alembic.
revision: str = 'f1bc0c47c1c2'
down_revision: Union[str, Sequence[str], None] = 'df109cbaef54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'telemetry_summary',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('flight_id', sa.Integer(), nullable=False),
        sa.Column('resolution_s', sa.Integer(), nullable=False),
        sa.Column('bucket_ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('avg_alt', sa.Float(), nullable=True),
        sa.Column('min_alt', sa.Float(), nullable=True),
        sa.Column('max_alt', sa.Float(), nullable=True),
        sa.Column('avg_groundspeed', sa.Float(), nullable=True),
        sa.Column('avg_battery_remaining', sa.Float(), nullable=True),
        sa.Column('min_battery_remaining', sa.Float(), nullable=True),
        sa.Column('sample_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['flight_id'], ['flights.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'flight_id', 'resolution_s', 'bucket_ts',
            name='uq_telsum_flt_res_bucket',
        ),
    )
    op.create_index(
        'idx_telsum_flt_res_bucket',
        'telemetry_summary',
        ['flight_id', 'resolution_s', 'bucket_ts'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('idx_telsum_flt_res_bucket', table_name='telemetry_summary')
    op.drop_table('telemetry_summary')
