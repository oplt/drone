"""add operational alerts

Revision ID: 8c4c9d6ef5a1
Revises: 3f2391ebb64e
Create Date: 2026-03-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8c4c9d6ef5a1"
down_revision: Union[str, Sequence[str], None] = "3f2391ebb64e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operational_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_type", sa.String(length=64), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("meta_data", sa.JSON(), nullable=False),
        sa.Column("first_triggered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by_user_id", sa.Integer(), nullable=True),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["acknowledged_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_operational_alerts_rule_type"), "operational_alerts", ["rule_type"], unique=False)
    op.create_index(op.f("ix_operational_alerts_dedupe_key"), "operational_alerts", ["dedupe_key"], unique=False)
    op.create_index(op.f("ix_operational_alerts_status"), "operational_alerts", ["status"], unique=False)
    op.create_index(op.f("ix_operational_alerts_acknowledged_by_user_id"), "operational_alerts", ["acknowledged_by_user_id"], unique=False)
    op.create_index("idx_operational_alert_status_triggered", "operational_alerts", ["status", "last_triggered_at"], unique=False)
    op.create_index("idx_operational_alert_rule_status", "operational_alerts", ["rule_type", "status"], unique=False)

    op.create_table(
        "alert_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("destination", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider_message_id", sa.String(length=128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["operational_alerts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_alert_deliveries_alert_id"), "alert_deliveries", ["alert_id"], unique=False)
    op.create_index(op.f("ix_alert_deliveries_channel"), "alert_deliveries", ["channel"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_alert_deliveries_channel"), table_name="alert_deliveries")
    op.drop_index(op.f("ix_alert_deliveries_alert_id"), table_name="alert_deliveries")
    op.drop_table("alert_deliveries")

    op.drop_index("idx_operational_alert_rule_status", table_name="operational_alerts")
    op.drop_index("idx_operational_alert_status_triggered", table_name="operational_alerts")
    op.drop_index(op.f("ix_operational_alerts_acknowledged_by_user_id"), table_name="operational_alerts")
    op.drop_index(op.f("ix_operational_alerts_status"), table_name="operational_alerts")
    op.drop_index(op.f("ix_operational_alerts_dedupe_key"), table_name="operational_alerts")
    op.drop_index(op.f("ix_operational_alerts_rule_type"), table_name="operational_alerts")
    op.drop_table("operational_alerts")
