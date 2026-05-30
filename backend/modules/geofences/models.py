from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    Float,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base


class Geofence(Base):
    __tablename__ = "geofences"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)

    # GeoAlchemy2 integration with Mapped
    polygon: Mapped[Geometry] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
        nullable=False,
    )

    min_alt_m: Mapped[float | None] = mapped_column(Float)
    max_alt_m: Mapped[float | None] = mapped_column(Float)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # This was the specific line causing your error:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
