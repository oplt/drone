"""Add independent sensor/gimbal aim constraints to scan targets."""

import sqlalchemy as sa
from alembic import op

revision = "h4c0d5e8f267"
down_revision = "g3b9c4d7e156"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("warehouse_scan_targets", sa.Column("sensor_aim_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("warehouse_scan_targets", "sensor_aim_json")
