"""Add canonical sensor-rig extrinsics document."""

import sqlalchemy as sa
from alembic import op

revision = "e1f7a2b5c934"
down_revision = "d9e6f1a4b823"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "warehouse_sensor_rigs",
        sa.Column("extrinsics_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    # URL-only legacy rigs cannot prove calibration contents.
    op.execute(
        "UPDATE warehouse_sensor_rigs SET calibration_status = 'missing', "
        "calibration_hash = NULL WHERE calibration_status = 'valid'"
    )


def downgrade() -> None:
    op.drop_column("warehouse_sensor_rigs", "extrinsics_json")
