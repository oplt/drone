"""Add agriculture mission plans and auditable preflight snapshots."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "z3c4d5e6f7a8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agriculture_mission_plans",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("source_plan_id", sa.String(64), sa.ForeignKey("agriculture_mission_plans.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("plan_hash", sa.String(128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("route_geojson", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("estimates_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("warnings_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("validation_errors_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('draft', 'validated', 'committed', 'superseded', 'invalid')", name="ck_agri_plan_status"),
    )
    op.create_index("ix_agriculture_mission_plans_field_id", "agriculture_mission_plans", ["field_id"])
    op.create_index("ix_agriculture_mission_plans_org_id", "agriculture_mission_plans", ["org_id"])
    op.create_index("ix_agriculture_mission_plans_status", "agriculture_mission_plans", ["status"])
    op.create_index("ix_agriculture_mission_plans_plan_hash", "agriculture_mission_plans", ["plan_hash"])
    op.create_index("idx_agri_plan_field_created", "agriculture_mission_plans", ["field_id", "created_at"])
    op.create_table(
        "agriculture_preflight_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("plan_id", sa.String(64), sa.ForeignKey("agriculture_mission_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flight_id", sa.String(64), sa.ForeignKey("agriculture_flights.id", ondelete="SET NULL")),
        sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("requested_by_user_id", sa.Integer()),
        sa.Column("status", sa.String(16), nullable=False, server_default="blocked"),
        sa.Column("fingerprint", sa.String(128), nullable=False),
        sa.Column("checks_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("acknowledged_by_user_id", sa.Integer()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('blocked', 'warning', 'pass', 'expired')", name="ck_agri_preflight_status"),
    )
    for name, columns in (
        ("ix_agriculture_preflight_snapshots_plan_id", ["plan_id"]),
        ("ix_agriculture_preflight_snapshots_flight_id", ["flight_id"]),
        ("ix_agriculture_preflight_snapshots_field_id", ["field_id"]),
        ("ix_agriculture_preflight_snapshots_org_id", ["org_id"]),
        ("ix_agriculture_preflight_snapshots_status", ["status"]),
        ("ix_agriculture_preflight_snapshots_fingerprint", ["fingerprint"]),
        ("ix_agriculture_preflight_snapshots_expires_at", ["expires_at"]),
        ("idx_agri_preflight_plan_created", ["plan_id", "created_at"]),
    ):
        op.create_index(name, "agriculture_preflight_snapshots", columns)


def downgrade() -> None:
    for name in (
        "idx_agri_preflight_plan_created",
        "ix_agriculture_preflight_snapshots_expires_at",
        "ix_agriculture_preflight_snapshots_fingerprint",
        "ix_agriculture_preflight_snapshots_status",
        "ix_agriculture_preflight_snapshots_org_id",
        "ix_agriculture_preflight_snapshots_field_id",
        "ix_agriculture_preflight_snapshots_flight_id",
        "ix_agriculture_preflight_snapshots_plan_id",
    ):
        op.drop_index(name, table_name="agriculture_preflight_snapshots")
    op.drop_table("agriculture_preflight_snapshots")
    for name in ("idx_agri_plan_field_created", "ix_agriculture_mission_plans_plan_hash", "ix_agriculture_mission_plans_status", "ix_agriculture_mission_plans_org_id", "ix_agriculture_mission_plans_field_id"):
        op.drop_index(name, table_name="agriculture_mission_plans")
    op.drop_table("agriculture_mission_plans")
