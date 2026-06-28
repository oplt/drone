"""add optimistic revision to warehouse layouts

Revision ID: j6e2f7a0b489
Revises: i5d1e6f9a378
"""

import sqlalchemy as sa
from alembic import op

revision = "j6e2f7a0b489"
down_revision = "i5d1e6f9a378"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "warehouse_layout_versions",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_warehouse_layout_revision_positive", "warehouse_layout_versions", "revision > 0"
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_warehouse_layout_revision_positive", "warehouse_layout_versions", type_="check"
    )
    op.drop_column("warehouse_layout_versions", "revision")
