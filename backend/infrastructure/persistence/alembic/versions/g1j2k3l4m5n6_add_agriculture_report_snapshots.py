"""Add immutable agriculture report snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "g1j2k3l4m5n6"
down_revision: str | Sequence[str] | None = "f6o7p8q9r0s1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agriculture_report_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_key", sa.String(64), nullable=False, server_default="standard"),
        sa.Column("template_version", sa.String(32), nullable=False, server_default="1.0"),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agriculture_report_snapshots_org_id", "agriculture_report_snapshots", ["org_id"])
    op.create_index("ix_agriculture_report_snapshots_field_id", "agriculture_report_snapshots", ["field_id"])
    op.create_index("ix_agriculture_report_snapshots_flight_id", "agriculture_report_snapshots", ["flight_id"])
    op.create_index("ix_agriculture_report_snapshots_run_id", "agriculture_report_snapshots", ["run_id"])
    op.create_index("ix_agriculture_report_snapshots_checksum", "agriculture_report_snapshots", ["checksum"])
    op.create_index("idx_agri_report_snapshot_run_time", "agriculture_report_snapshots", ["run_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_agri_report_snapshot_run_time", table_name="agriculture_report_snapshots")
    op.drop_index("ix_agriculture_report_snapshots_checksum", table_name="agriculture_report_snapshots")
    op.drop_index("ix_agriculture_report_snapshots_run_id", table_name="agriculture_report_snapshots")
    op.drop_index("ix_agriculture_report_snapshots_flight_id", table_name="agriculture_report_snapshots")
    op.drop_index("ix_agriculture_report_snapshots_field_id", table_name="agriculture_report_snapshots")
    op.drop_index("ix_agriculture_report_snapshots_org_id", table_name="agriculture_report_snapshots")
    op.drop_table("agriculture_report_snapshots")
