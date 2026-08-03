"""Add bounded agriculture assistant audit records."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6f7a8b9c0d1"
down_revision: str | Sequence[str] | None = "b5e6f7a8b9c0d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agriculture_assistant_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task", sa.String(32), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="fallback"),
        sa.Column("decision_status", sa.String(32), nullable=False, server_default="provider_unavailable"), sa.Column("prompt_version", sa.String(64), nullable=False), sa.Column("prompt_hash", sa.String(128), nullable=False), sa.Column("context_checksum", sa.String(128), nullable=False), sa.Column("question_redacted", sa.Text(), nullable=False),
        sa.Column("source_ids", sa.JSON(), nullable=False, server_default="[]"), sa.Column("deterministic_rules", sa.JSON(), nullable=False, server_default="[]"), sa.Column("output", sa.JSON(), nullable=False, server_default="{}"), sa.Column("citations", sa.JSON(), nullable=False, server_default="[]"), sa.Column("limitations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"), sa.Column("risk_level", sa.String(16), nullable=False, server_default="high"), sa.Column("requires_human_approval", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("abstained", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("profile_id", sa.String(128)), sa.Column("model", sa.String(256)), sa.Column("error_code", sa.String(128)),
        sa.Column("review_status", sa.String(24), nullable=False, server_default="pending"), sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("review_note", sa.Text()), sa.Column("reviewed_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for name, columns in (("ix_agri_assistant_org", ["org_id"]), ("ix_agri_assistant_field", ["field_id"]), ("ix_agri_assistant_flight", ["flight_id"]), ("ix_agri_assistant_run", ["run_id"]), ("ix_agri_assistant_status", ["status"]), ("ix_agri_assistant_review", ["review_status"]), ("idx_agri_assistant_run_time", ["run_id", "created_at"])):
        op.create_index(name, "agriculture_assistant_runs", columns)


def downgrade() -> None:
    for name in ("idx_agri_assistant_run_time", "ix_agri_assistant_review", "ix_agri_assistant_status", "ix_agri_assistant_run", "ix_agri_assistant_flight", "ix_agri_assistant_field", "ix_agri_assistant_org"):
        op.drop_index(name, table_name="agriculture_assistant_runs")
    op.drop_table("agriculture_assistant_runs")
