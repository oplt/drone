"""Add P3 agronomic findings, outcomes, and comparison metadata.

Revision ID: g0h1i2j3k4l5
Revises: f9g0h1i2j3k4
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g0h1i2j3k4l5"
down_revision: str | Sequence[str] | None = "f9g0h1i2j3k4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agriculture_observations",
        sa.Column("merged_into_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "agriculture_observations",
        sa.Column("split_from_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "agriculture_observations",
        sa.Column("member_observation_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.create_foreign_key(
        "fk_agri_obs_merged_into",
        "agriculture_observations",
        "agriculture_observations",
        ["merged_into_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agri_obs_split_from",
        "agriculture_observations",
        "agriculture_observations",
        ["split_from_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_agriculture_observations_merged_into_id", "agriculture_observations", ["merged_into_id"])
    op.create_index("ix_agriculture_observations_split_from_id", "agriculture_observations", ["split_from_id"])

    op.create_table(
        "agriculture_field_outcomes",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flight_id", sa.String(length=64), sa.ForeignKey("agriculture_flights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("agriculture_analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("observation_id", sa.String(length=64), sa.ForeignKey("agriculture_observations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("outcome_status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(length=160), nullable=True),
        sa.Column("capability_release_id", sa.String(length=64), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_agriculture_field_outcomes_org_id", "agriculture_field_outcomes", ["org_id"])
    op.create_index("ix_agriculture_field_outcomes_field_id", "agriculture_field_outcomes", ["field_id"])
    op.create_index("ix_agriculture_field_outcomes_flight_id", "agriculture_field_outcomes", ["flight_id"])
    op.create_index("ix_agriculture_field_outcomes_run_id", "agriculture_field_outcomes", ["run_id"])
    op.create_index("ix_agriculture_field_outcomes_observation_id", "agriculture_field_outcomes", ["observation_id"])
    op.create_index("ix_agriculture_field_outcomes_outcome_status", "agriculture_field_outcomes", ["outcome_status"])
    op.create_index("ix_agriculture_field_outcomes_capability_release_id", "agriculture_field_outcomes", ["capability_release_id"])
    op.create_index("ix_agriculture_field_outcomes_created_by_user_id", "agriculture_field_outcomes", ["created_by_user_id"])
    op.create_index(
        "idx_agri_field_outcome_run_obs",
        "agriculture_field_outcomes",
        ["run_id", "observation_id", "created_at"],
    )

    op.add_column(
        "agriculture_flight_alignments",
        sa.Column("comparability", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("agriculture_flight_alignments", "comparability")
    op.drop_index("idx_agri_field_outcome_run_obs", table_name="agriculture_field_outcomes")
    op.drop_index("ix_agriculture_field_outcomes_created_by_user_id", table_name="agriculture_field_outcomes")
    op.drop_index("ix_agriculture_field_outcomes_capability_release_id", table_name="agriculture_field_outcomes")
    op.drop_index("ix_agriculture_field_outcomes_outcome_status", table_name="agriculture_field_outcomes")
    op.drop_index("ix_agriculture_field_outcomes_observation_id", table_name="agriculture_field_outcomes")
    op.drop_index("ix_agriculture_field_outcomes_run_id", table_name="agriculture_field_outcomes")
    op.drop_index("ix_agriculture_field_outcomes_flight_id", table_name="agriculture_field_outcomes")
    op.drop_index("ix_agriculture_field_outcomes_field_id", table_name="agriculture_field_outcomes")
    op.drop_index("ix_agriculture_field_outcomes_org_id", table_name="agriculture_field_outcomes")
    op.drop_table("agriculture_field_outcomes")
    op.drop_index("ix_agriculture_observations_split_from_id", table_name="agriculture_observations")
    op.drop_index("ix_agriculture_observations_merged_into_id", table_name="agriculture_observations")
    op.drop_constraint("fk_agri_obs_split_from", "agriculture_observations", type_="foreignkey")
    op.drop_constraint("fk_agri_obs_merged_into", "agriculture_observations", type_="foreignkey")
    op.drop_column("agriculture_observations", "member_observation_ids")
    op.drop_column("agriculture_observations", "split_from_id")
    op.drop_column("agriculture_observations", "merged_into_id")
