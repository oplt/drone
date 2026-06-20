"""agent_runs audit table

Revision ID: 20260618_agent_runs
Revises: 20260613_warehouse_inspection
Create Date: 2026-06-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260618_agent_runs"
down_revision: str | Sequence[str] | None = "20260613_warehouse_inspection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mission_runtime_id", sa.Integer(), nullable=True),
        sa.Column("agent_id", sa.String(length=80), nullable=False),
        sa.Column("phase", sa.String(length=40), nullable=False),
        sa.Column("llm_task", sa.String(length=80), nullable=False),
        sa.Column("profile_id", sa.String(length=120), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("prompt_hash", sa.String(length=128), nullable=False),
        sa.Column("response_preview", sa.Text(), nullable=True),
        sa.Column("structured_result", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_runs_agent_id"), "agent_runs", ["agent_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_created_at"), "agent_runs", ["created_at"], unique=False)
    op.create_index(op.f("ix_agent_runs_mission_runtime_id"), "agent_runs", ["mission_runtime_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_phase"), "agent_runs", ["phase"], unique=False)
    op.create_index(op.f("ix_agent_runs_status"), "agent_runs", ["status"], unique=False)
    op.create_index("idx_agent_runs_mission_agent", "agent_runs", ["mission_runtime_id", "agent_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_agent_runs_mission_agent", table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_status"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_phase"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_mission_runtime_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_created_at"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_agent_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
