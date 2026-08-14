"""Add reviewed agriculture intervention zones.

Revision ID: n7o8p9q0r1s2
Revises: m6n7o8p9q0r1
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "n7o8p9q0r1s2"
down_revision: str | Sequence[str] | None = "m6n7o8p9q0r1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agriculture_intervention_zones",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column(
            "field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "flight_id",
            sa.String(64),
            sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.String(64),
            sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("geometry_geojson", sa.JSON(), nullable=False),
        sa.Column("area_m2", sa.Float(), nullable=False),
        sa.Column("source_observation_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("model_versions", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="proposed"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column(
            "reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("review_note", sa.Text()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'approved', 'rejected')",
            name="ck_agri_intervention_zone_status",
        ),
        sa.CheckConstraint("area_m2 > 0", name="ck_agri_intervention_zone_area"),
    )
    for name, columns in (
        ("ix_agri_intervention_zone_org", ["org_id"]),
        ("ix_agri_intervention_zone_field", ["field_id"]),
        ("ix_agri_intervention_zone_flight", ["flight_id"]),
        ("ix_agri_intervention_zone_run", ["run_id"]),
        ("ix_agri_intervention_zone_status", ["status"]),
        ("ix_agri_intervention_zone_creator", ["created_by_user_id"]),
        ("ix_agri_intervention_zone_reviewer", ["reviewed_by_user_id"]),
        ("idx_agri_intervention_run_status", ["run_id", "status"]),
    ):
        op.create_index(name, "agriculture_intervention_zones", columns)


def downgrade() -> None:
    op.drop_table("agriculture_intervention_zones")
