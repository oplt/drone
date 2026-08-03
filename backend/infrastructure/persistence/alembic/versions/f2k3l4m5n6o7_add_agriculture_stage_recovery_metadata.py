"""Persist per-stage worker retry and dead-letter metadata."""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "f2k3l4m5n6o7"
down_revision: str | Sequence[str] | None = "f1j2k3l4m5n6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agriculture_analysis_stages", sa.Column("task_id", sa.String(128)))
    op.add_column("agriculture_analysis_stages", sa.Column("queue_name", sa.String(128)))
    op.add_column("agriculture_analysis_stages", sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("agriculture_analysis_stages", sa.Column("dead_letter", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("agriculture_analysis_stages", sa.Column("last_error_at", sa.DateTime(timezone=True)))
    op.add_column("agriculture_analysis_stages", sa.Column("dead_letter_at", sa.DateTime(timezone=True)))
    op.create_index("ix_agriculture_analysis_stages_task_id", "agriculture_analysis_stages", ["task_id"])
    op.create_index("ix_agriculture_analysis_stages_queue_name", "agriculture_analysis_stages", ["queue_name"])
    op.create_index("ix_agriculture_analysis_stages_dead_letter", "agriculture_analysis_stages", ["dead_letter"])


def downgrade() -> None:
    op.drop_index("ix_agriculture_analysis_stages_dead_letter", table_name="agriculture_analysis_stages")
    op.drop_index("ix_agriculture_analysis_stages_queue_name", table_name="agriculture_analysis_stages")
    op.drop_index("ix_agriculture_analysis_stages_task_id", table_name="agriculture_analysis_stages")
    op.drop_column("agriculture_analysis_stages", "dead_letter_at")
    op.drop_column("agriculture_analysis_stages", "last_error_at")
    op.drop_column("agriculture_analysis_stages", "dead_letter")
    op.drop_column("agriculture_analysis_stages", "retryable")
    op.drop_column("agriculture_analysis_stages", "queue_name")
    op.drop_column("agriculture_analysis_stages", "task_id")
