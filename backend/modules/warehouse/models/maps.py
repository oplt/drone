"""Warehouse ORM — map root aggregate."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from geoalchemy2 import Geometry
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database.base import Base

if TYPE_CHECKING:
    from .coordinate_frames import WarehouseCoordinateFrame
    from .docks import WarehouseDockStation
    from .inspection import WarehouseInspectionMission, WarehouseScanTarget
    from .mapping_models import WarehouseModel
    from .rack_templates import WarehouseRackTemplate


class WarehouseMap(Base):
    __tablename__ = "warehouse_maps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, index=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # nullable=True: indoor warehouse maps use polygon_local_m stored in meta_data
    boundary: Mapped[Geometry | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
        nullable=True,
    )
    area_m2: Mapped[float | None] = mapped_column(Float)
    centroid: Mapped[Geometry | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )
    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    models: Mapped[list[WarehouseModel]] = relationship(
        back_populates="warehouse_map",
        cascade="all, delete-orphan",
    )
    docks: Mapped[list[WarehouseDockStation]] = relationship(
        back_populates="warehouse_map",
        cascade="all, delete-orphan",
    )
    scan_targets: Mapped[list[WarehouseScanTarget]] = relationship(
        back_populates="warehouse_map",
        cascade="all, delete-orphan",
    )
    inspection_missions: Mapped[list[WarehouseInspectionMission]] = relationship(
        back_populates="warehouse_map",
        cascade="all, delete-orphan",
    )
    coordinate_frames: Mapped[list[WarehouseCoordinateFrame]] = relationship(
        back_populates="warehouse_map", cascade="all, delete-orphan"
    )
    rack_templates: Mapped[list[WarehouseRackTemplate]] = relationship(
        back_populates="warehouse_map", cascade="all, delete-orphan"
    )


__all__ = ["WarehouseMap"]
