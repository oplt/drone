"""Warehouse ORM — dock stations."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database.base import Base

if TYPE_CHECKING:
    from .maps import WarehouseMap


class WarehouseDockStation(Base):
    __tablename__ = "warehouse_dock_stations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_map_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_maps.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    marker_id: Mapped[str | None] = mapped_column(String(128), index=True)
    charger_type: Mapped[str | None] = mapped_column(String(64))
    pose_local_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    entry_pose_local_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    exit_pose_local_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    warehouse_map: Mapped[WarehouseMap] = relationship(back_populates="docks")

    __table_args__ = (
        Index(
            "uq_warehouse_dock_station_map_name_active",
            "warehouse_map_id",
            "name",
            unique=True,
            postgresql_where=text("active IS TRUE"),
        ),
        Index("idx_warehouse_dock_station_map_active", "warehouse_map_id", "active"),
    )


__all__ = ["WarehouseDockStation"]
