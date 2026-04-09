"""add covering index on mavlink_event for msg_type replay queries

Revision ID: df109cbaef54
Revises: d1b112563cfe
Create Date: 2026-04-07 08:45:21.428951

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "df109cbaef54"
down_revision: str | Sequence[str] | None = "d1b112563cfe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_evt_flt_type_ts",
        "mavlink_event",
        ["flight_id", "msg_type", "timestamp"],
        unique=False,
        postgresql_include=["time_boot_ms", "time_unix_usec"],
    )


def downgrade() -> None:
    op.drop_index("idx_evt_flt_type_ts", table_name="mavlink_event")
