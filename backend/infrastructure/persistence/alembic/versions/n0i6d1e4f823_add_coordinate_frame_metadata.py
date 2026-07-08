"""add coordinate frame metadata

Revision ID: n0i6d1e4f823
Revises: m9h5c0d3e712
Create Date: 2026-07-08 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "n0i6d1e4f823"
down_revision: Union[str, Sequence[str], None] = "m9h5c0d3e712"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "warehouse_coordinate_frames",
        sa.Column("meta_data", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.alter_column("warehouse_coordinate_frames", "meta_data", server_default=None)


def downgrade() -> None:
    op.drop_column("warehouse_coordinate_frames", "meta_data")
