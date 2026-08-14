"""Add explicit stand and weed analytics configuration.

Revision ID: o8p9q0r1s2t3
Revises: n7o8p9q0r1s2
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "o8p9q0r1s2t3"
down_revision: str | Sequence[str] | None = "n7o8p9q0r1s2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agriculture_field_profiles",
        sa.Column("expected_plant_spacing_m", sa.Float(), nullable=True),
    )
    op.add_column(
        "agriculture_field_profiles",
        sa.Column("stand_gap_multiplier", sa.Float(), nullable=False, server_default="1.75"),
    )
    op.add_column(
        "agriculture_field_profiles",
        sa.Column("weed_density_cell_m", sa.Float(), nullable=False, server_default="10"),
    )
    op.add_column(
        "agriculture_field_profiles",
        sa.Column("weed_hotspot_percentile", sa.Float(), nullable=False, server_default="0.8"),
    )
    op.create_check_constraint(
        "ck_agri_profile_plant_spacing",
        "agriculture_field_profiles",
        "expected_plant_spacing_m IS NULL OR "
        "(expected_plant_spacing_m > 0 AND expected_plant_spacing_m <= 10)",
    )
    op.create_check_constraint(
        "ck_agri_profile_stand_gap_multiplier",
        "agriculture_field_profiles",
        "stand_gap_multiplier > 1 AND stand_gap_multiplier <= 10",
    )
    op.create_check_constraint(
        "ck_agri_profile_weed_density_cell",
        "agriculture_field_profiles",
        "weed_density_cell_m >= 2 AND weed_density_cell_m <= 100",
    )
    op.create_check_constraint(
        "ck_agri_profile_weed_hotspot_percentile",
        "agriculture_field_profiles",
        "weed_hotspot_percentile > 0 AND weed_hotspot_percentile <= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agri_profile_weed_hotspot_percentile",
        "agriculture_field_profiles",
        type_="check",
    )
    op.drop_constraint(
        "ck_agri_profile_weed_density_cell",
        "agriculture_field_profiles",
        type_="check",
    )
    op.drop_constraint(
        "ck_agri_profile_stand_gap_multiplier",
        "agriculture_field_profiles",
        type_="check",
    )
    op.drop_constraint(
        "ck_agri_profile_plant_spacing",
        "agriculture_field_profiles",
        type_="check",
    )
    op.drop_column("agriculture_field_profiles", "weed_hotspot_percentile")
    op.drop_column("agriculture_field_profiles", "weed_density_cell_m")
    op.drop_column("agriculture_field_profiles", "stand_gap_multiplier")
    op.drop_column("agriculture_field_profiles", "expected_plant_spacing_m")
