"""Persistence columns owned by the Phase 5 field analytics configuration."""

from sqlalchemy import Float
from sqlalchemy.orm import Mapped, mapped_column


class AgricultureAnalyticsProfileColumns:
    """Declarative mixin shared by the canonical agriculture field profile."""

    expected_plant_spacing_m: Mapped[float | None] = mapped_column(Float)
    stand_gap_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.75)
    weed_density_cell_m: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    weed_hotspot_percentile: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
