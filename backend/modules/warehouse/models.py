from __future__ import annotations

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database.base import Base


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
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=True,
    )
    area_m2: Mapped[float | None] = mapped_column(Float)
    centroid: Mapped[Geometry | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
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
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    warehouse_map: Mapped[WarehouseMap] = relationship(back_populates="docks")

    __table_args__ = (
        UniqueConstraint("warehouse_map_id", "name", name="uq_warehouse_dock_station_name"),
    )


class WarehouseModel(Base):
    __tablename__ = "warehouse_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_map_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_maps.id", ondelete="CASCADE"),
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    epsg: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    warehouse_map: Mapped[WarehouseMap] = relationship(back_populates="models")
    jobs: Mapped[list[WarehouseMappingJob]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )
    assets: Mapped[list[WarehouseAsset]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("warehouse_map_id", "version", name="uq_warehouse_model_version"),
        Index("idx_warehouse_model_status", "status"),
    )


class WarehouseMappingJob(Base):
    __tablename__ = "warehouse_mapping_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_map_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_maps.id", ondelete="CASCADE"),
        index=True,
    )
    model_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_models.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processor: Mapped[str] = mapped_column(String(32), nullable=False, default="warehouse_scan")
    processor_task_id: Mapped[str | None] = mapped_column(String(64), index=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    model: Mapped[WarehouseModel] = relationship(back_populates="jobs")

    __table_args__ = (Index("idx_warehouse_mapping_job_status", "status"),)


class WarehouseAsset(Base):
    __tablename__ = "warehouse_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_models.id", ondelete="CASCADE"),
        index=True,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum: Mapped[str | None] = mapped_column(String(128))
    bbox: Mapped[Geometry | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=True,
    )
    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    model: Mapped[WarehouseModel] = relationship(back_populates="assets")

    __table_args__ = (Index("idx_warehouse_asset_model_type", "model_id", "type"),)


# ---------------------------------------------------------------------------
# Mission runtime persistence
# ---------------------------------------------------------------------------
