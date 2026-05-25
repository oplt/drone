"""add async outbox and webhook idempotency

Revision ID: f2c3d4e5a6b7
Revises: e5f6a7b8c9d0
Create Date: 2026-05-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2c3d4e5a6b7"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_outbox_event_type", "outbox_events", ["event_type"])
    op.create_index("idx_outbox_event_status", "outbox_events", ["status"])
    op.create_index("idx_outbox_pending_available", "outbox_events", ["status", "available_at"])
    op.add_column("webhook_deliveries", sa.Column("idempotency_key", sa.String(255), nullable=True))
    op.create_unique_constraint(
        "uq_webhook_delivery_idempotency_key", "webhook_deliveries", ["idempotency_key"]
    )
    op.add_column("alert_deliveries", sa.Column("idempotency_key", sa.String(255), nullable=True))
    op.create_unique_constraint(
        "uq_alert_delivery_idempotency_key", "alert_deliveries", ["idempotency_key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_alert_delivery_idempotency_key", "alert_deliveries", type_="unique")
    op.drop_column("alert_deliveries", "idempotency_key")
    op.drop_constraint("uq_webhook_delivery_idempotency_key", "webhook_deliveries", type_="unique")
    op.drop_column("webhook_deliveries", "idempotency_key")
    op.drop_table("outbox_events")
