"""Warehouse ORM — scanned map models, jobs, and assets."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    BigInteger,
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

if TYPE_CHECKING:
    from .maps import WarehouseMap


class WarehouseModel(Base):
    __tablename__ = "warehouse_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_map_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_maps.id", ondelete="CASCADE"),
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    coordinate_frame_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_coordinate_frames.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
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
    algorithm_version: Mapped[str] = mapped_column(
        String(128), nullable=False, default="unknown", index=True
    )
    input_checksum: Mapped[str | None] = mapped_column(String(128), index=True)
    extraction_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    failure_reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
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
    coordinate_frame_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_coordinate_frames.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    frame_id: Mapped[str] = mapped_column(String(64), nullable=False, default="odom")
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum: Mapped[str | None] = mapped_column(String(128))
    bbox: Mapped[Geometry | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
        nullable=True,
    )
    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    model: Mapped[WarehouseModel] = relationship(back_populates="assets")

    __table_args__ = (Index("idx_warehouse_asset_model_type", "model_id", "type"),)


class WarehouseScanArtifactSet(Base):
    __tablename__ = "warehouse_scan_artifact_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_map_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_maps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    map_model_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_models.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    coordinate_frame_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_coordinate_frames.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sensor_rig_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_sensor_rigs.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    calibration_hash: Mapped[str | None] = mapped_column(String(128))
    client_flight_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    inputs_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    extraction_params_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = [
    "WarehouseAsset",
    "WarehouseMappingJob",
    "WarehouseModel",
    "WarehouseScanArtifactSet",
]
