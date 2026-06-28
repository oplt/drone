"""Add inspection preview approval and runtime policy.

Revision ID: m9h5c0d3e712
Revises: l8g4b9c2d601
"""

import sqlalchemy as sa
from alembic import op

revision = "m9h5c0d3e712"
down_revision = "l8g4b9c2d601"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("warehouse_inspection_missions", sa.Column("plan_checksum", sa.String(64)))
    op.add_column(
        "warehouse_inspection_missions",
        sa.Column("approval_status", sa.String(24), nullable=False, server_default="pending"),
    )
    op.add_column(
        "warehouse_inspection_missions", sa.Column("approved_at", sa.DateTime(timezone=True))
    )
    op.add_column("warehouse_inspection_missions", sa.Column("approved_by_id", sa.Integer()))
    op.add_column(
        "warehouse_inspection_missions",
        sa.Column("runtime_policy_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_warehouse_inspection_missions_plan_checksum",
        "warehouse_inspection_missions",
        ["plan_checksum"],
    )
    op.create_index(
        "ix_warehouse_inspection_missions_approval_status",
        "warehouse_inspection_missions",
        ["approval_status"],
    )
    op.create_check_constraint(
        "ck_warehouse_inspection_mission_approval",
        "warehouse_inspection_missions",
        "approval_status IN ('pending','approved','rejected')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_warehouse_inspection_mission_approval", "warehouse_inspection_missions", type_="check"
    )
    op.drop_index(
        "ix_warehouse_inspection_missions_approval_status",
        table_name="warehouse_inspection_missions",
    )
    op.drop_index(
        "ix_warehouse_inspection_missions_plan_checksum", table_name="warehouse_inspection_missions"
    )
    for column in (
        "runtime_policy_json",
        "approved_by_id",
        "approved_at",
        "approval_status",
        "plan_checksum",
    ):
        op.drop_column("warehouse_inspection_missions", column)
