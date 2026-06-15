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
    text,
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


class WarehouseSensorRig(Base):
    __tablename__ = "warehouse_sensor_rigs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, index=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    camera_model: Mapped[str] = mapped_column(String(128), nullable=False)
    stereo_baseline_m: Mapped[float | None] = mapped_column(Float)
    intrinsics_url: Mapped[str | None] = mapped_column(String(2048))
    extrinsics_url: Mapped[str | None] = mapped_column(String(2048))
    imu_transform_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    firmware_version: Mapped[str | None] = mapped_column(String(128))
    isaac_ros_version: Mapped[str | None] = mapped_column(String(128))
    calibration_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="missing", index=True
    )
    calibration_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    calibration_meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_warehouse_sensor_rig_org_name_active",
            "org_id",
            "name",
            unique=True,
            postgresql_where=text("active IS TRUE AND org_id IS NOT NULL"),
        ),
        Index(
            "uq_warehouse_sensor_rig_owner_name_active",
            "owner_id",
            "name",
            unique=True,
            postgresql_where=text("active IS TRUE AND org_id IS NULL"),
        ),
        Index("idx_warehouse_sensor_rig_org_active", "org_id", "active"),
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
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
        nullable=True,
    )
    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    model: Mapped[WarehouseModel] = relationship(back_populates="assets")

    __table_args__ = (Index("idx_warehouse_asset_model_type", "model_id", "type"),)


# ---------------------------------------------------------------------------
# Warehouse product/barcode inspection persistence
# ---------------------------------------------------------------------------


class WarehouseScanTarget(Base):
    __tablename__ = "warehouse_scan_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_map_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_maps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reference_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_models.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dock_station_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_dock_stations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    aisle_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rack_code: Mapped[str | None] = mapped_column(String(64))
    shelf_level: Mapped[int | None] = mapped_column(Integer)
    bin_code: Mapped[str | None] = mapped_column(String(64))
    sku: Mapped[str | None] = mapped_column(String(128), index=True)
    barcode: Mapped[str | None] = mapped_column(String(128), index=True)
    product_name: Mapped[str | None] = mapped_column(String(255))
    target_point_local_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    scan_pose_local_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    shelf_normal_local_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    standoff_m: Mapped[float] = mapped_column(Float, default=1.2, nullable=False)
    hover_time_s: Mapped[float] = mapped_column(Float, default=3.0, nullable=False)
    scan_timeout_s: Mapped[float] = mapped_column(Float, default=8.0, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    warehouse_map: Mapped[WarehouseMap] = relationship(back_populates="scan_targets")

    __table_args__ = (
        Index("idx_warehouse_scan_target_map_active", "warehouse_map_id", "active"),
        Index(
            "idx_warehouse_scan_target_location",
            "warehouse_map_id",
            "aisle_code",
            "rack_code",
            "bin_code",
        ),
    )


class WarehouseInspectionMission(Base):
    __tablename__ = "warehouse_inspection_missions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_map_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_maps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="planned", nullable=False, index=True)
    scan_mode: Mapped[str] = mapped_column(String(32), default="barcode", nullable=False)
    return_to_dock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    target_ids_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    warehouse_map: Mapped[WarehouseMap] = relationship(back_populates="inspection_missions")
    results: Mapped[list[WarehouseInspectionResult]] = relationship(
        back_populates="mission",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "idx_warehouse_inspection_mission_map_status",
            "warehouse_map_id",
            "status",
        ),
    )


class WarehouseInspectionResult(Base):
    __tablename__ = "warehouse_inspection_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mission_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_inspection_missions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_scan_targets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    expected_barcode: Mapped[str | None] = mapped_column(String(128))
    detected_barcode: Mapped[str | None] = mapped_column(String(128))
    confidence: Mapped[float | None] = mapped_column(Float)
    image_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    video_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    drone_pose_local_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    mission: Mapped[WarehouseInspectionMission] = relationship(back_populates="results")

    __table_args__ = (
        Index(
            "idx_warehouse_inspection_result_mission_target",
            "mission_id",
            "target_id",
        ),
    )
