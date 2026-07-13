"""Add indexes for dashboard, runtime, telemetry, and webhook request paths."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "t6a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "s5n1j9g4e820"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("idx_telemetry_created_at", "telemetry", ["created_at"])
    op.create_index("idx_flights_started_at", "flights", ["started_at"])
    op.create_index("idx_flights_ended_at", "flights", ["ended_at"])
    op.create_index(
        "idx_mission_runtime_client_state",
        "mission_runtimes",
        ["client_flight_id", "state"],
    )
    op.create_index(
        "idx_webhook_delivery_endpoint_status_created",
        "webhook_deliveries",
        ["endpoint_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_webhook_delivery_endpoint_status_created", table_name="webhook_deliveries")
    op.drop_index("idx_mission_runtime_client_state", table_name="mission_runtimes")
    op.drop_index("idx_flights_ended_at", table_name="flights")
    op.drop_index("idx_flights_started_at", table_name="flights")
    op.drop_index("idx_telemetry_created_at", table_name="telemetry")
