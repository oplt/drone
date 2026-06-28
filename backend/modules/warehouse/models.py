from __future__ import annotations

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
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
    coordinate_frames: Mapped[list[WarehouseCoordinateFrame]] = relationship(
        back_populates="warehouse_map", cascade="all, delete-orphan"
    )


class WarehouseCoordinateFrame(Base):
    """Immutable, auditable warehouse_map localization revision.

    ``transform_json`` is the pose of the ``odom`` child in ``warehouse_map``
    (translation + unit quaternion), matching ROS TF parent/child semantics.
    It therefore converts odom points into stable warehouse_map coordinates.
    """

    __tablename__ = "warehouse_coordinate_frames"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_map_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_maps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_frame_id: Mapped[str] = mapped_column(
        String(64), default="warehouse_map", nullable=False
    )
    child_frame_id: Mapped[str] = mapped_column(String(64), default="odom", nullable=False)
    units: Mapped[str] = mapped_column(String(16), default="m", nullable=False)
    axis_convention: Mapped[str] = mapped_column(String(16), default="ENU", nullable=False)
    handedness: Mapped[str] = mapped_column(String(16), default="right", nullable=False)
    transform_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    covariance_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    localization_method: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    transform_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_age_s: Mapped[float] = mapped_column(Float, nullable=False, default=300.0)
    transform_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    warehouse_map: Mapped[WarehouseMap] = relationship(back_populates="coordinate_frames")

    __table_args__ = (
        CheckConstraint("units = 'm'", name="ck_warehouse_coordinate_frame_units"),
        CheckConstraint(
            "axis_convention = 'ENU' AND handedness = 'right'",
            name="ck_warehouse_coordinate_frame_axes",
        ),
        CheckConstraint(
            "status IN ('draft', 'locked', 'superseded')",
            name="ck_warehouse_coordinate_frame_status",
        ),
        UniqueConstraint(
            "warehouse_map_id", "version", name="uq_warehouse_coordinate_frame_version"
        ),
        Index("idx_warehouse_coordinate_frame_map_status", "warehouse_map_id", "status"),
        Index(
            "uq_warehouse_coordinate_frame_locked",
            "warehouse_map_id",
            unique=True,
            postgresql_where=text("status = 'locked'"),
        ),
    )


class WarehouseMapSetupVersion(Base):
    __tablename__ = "warehouse_map_setup_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_map_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_maps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    coordinate_frame_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_coordinate_frames.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    polygon_local_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    origin_transform_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    alignment_deg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    alignment_reference: Mapped[str] = mapped_column(String(24), nullable=False, default="aisle")
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    map_resolution_m: Mapped[float | None] = mapped_column(Float)
    scale: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    scale_calibration_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    transform_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_transform_age_s: Mapped[float] = mapped_column(Float, nullable=False, default=300.0)
    covariance_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    localization_method: Mapped[str] = mapped_column(String(64), nullable=False, default="operator")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("warehouse_map_id", "version", name="uq_warehouse_map_setup_version"),
        CheckConstraint(
            "status IN ('draft', 'locked', 'superseded')",
            name="ck_warehouse_map_setup_status",
        ),
        CheckConstraint(
            "alignment_reference IN ('north', 'aisle')",
            name="ck_warehouse_map_setup_alignment_reference",
        ),
        CheckConstraint("scale = 1.0", name="ck_warehouse_map_setup_scale"),
        CheckConstraint(
            "map_resolution_m IS NULL OR map_resolution_m > 0",
            name="ck_warehouse_map_setup_resolution",
        ),
        Index(
            "uq_warehouse_map_setup_locked",
            "warehouse_map_id",
            unique=True,
            postgresql_where=text("status = 'locked'"),
        ),
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
    extrinsics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
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


# ---------------------------------------------------------------------------
# Warehouse product/barcode inspection persistence
# ---------------------------------------------------------------------------


class WarehouseLayoutVersion(Base):
    __tablename__ = "warehouse_layout_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_map_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_maps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    coordinate_frame_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_coordinate_frames.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    map_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_models.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    artifact_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_scan_artifact_sets.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    input_checksum: Mapped[str | None] = mapped_column(String(64))
    algorithm_version: Mapped[str | None] = mapped_column(String(64))
    provenance_status: Mapped[str] = mapped_column(
        String(24), default="auto", nullable=False, index=True
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("warehouse_map_id", "version", name="uq_warehouse_layout_version"),
        CheckConstraint(
            "status IN ('draft', 'locked', 'superseded')",
            name="ck_warehouse_layout_version_status",
        ),
        CheckConstraint(
            "provenance_status IN ('auto', 'manual', 'confirmed')",
            name="ck_warehouse_layout_provenance",
        ),
        Index(
            "uq_warehouse_layout_locked",
            "warehouse_map_id",
            unique=True,
            postgresql_where=text("status = 'locked'"),
        ),
    )


class WarehouseAisle(Base):
    __tablename__ = "warehouse_aisles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    layout_version_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_layout_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    provenance_status: Mapped[str] = mapped_column(String(24), default="auto", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (
        UniqueConstraint("layout_version_id", "code", name="uq_warehouse_aisle_code"),
        CheckConstraint(
            "provenance_status IN ('auto', 'manual', 'confirmed')",
            name="ck_warehouse_aisle_provenance",
        ),
    )


class WarehouseRack(Base):
    __tablename__ = "warehouse_racks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aisle_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_aisles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    provenance_status: Mapped[str] = mapped_column(String(24), default="auto", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (
        UniqueConstraint("aisle_id", "code", name="uq_warehouse_rack_code"),
        CheckConstraint(
            "provenance_status IN ('auto', 'manual', 'confirmed')",
            name="ck_warehouse_rack_provenance",
        ),
    )


class WarehouseShelf(Base):
    __tablename__ = "warehouse_shelves"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rack_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_racks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    provenance_status: Mapped[str] = mapped_column(String(24), default="auto", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (
        UniqueConstraint("rack_id", "level", name="uq_warehouse_shelf_level"),
        CheckConstraint(
            "provenance_status IN ('auto', 'manual', 'confirmed')",
            name="ck_warehouse_shelf_provenance",
        ),
    )


class WarehouseBin(Base):
    __tablename__ = "warehouse_bins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shelf_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_shelves.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    geometry_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    provenance_status: Mapped[str] = mapped_column(String(24), default="auto", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (
        UniqueConstraint("shelf_id", "code", name="uq_warehouse_bin_code"),
        CheckConstraint(
            "provenance_status IN ('auto', 'manual', 'confirmed')",
            name="ck_warehouse_bin_provenance",
        ),
    )


class WarehouseSafetyZone(Base):
    __tablename__ = "warehouse_safety_zones"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    layout_version_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_layout_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    geometry_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    min_z_m: Mapped[float | None] = mapped_column(Float)
    max_z_m: Mapped[float | None] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    __table_args__ = (
        UniqueConstraint("layout_version_id", "code", name="uq_warehouse_safety_zone_code"),
        CheckConstraint(
            "kind IN ('no_fly', 'keep_out', 'slow', 'landing')",
            name="ck_warehouse_safety_zone_kind",
        ),
    )


class WarehouseLayoutCandidate(Base):
    __tablename__ = "warehouse_layout_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_map_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_maps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    layout_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_layout_versions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    entity_kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    identity_key: Mapped[str] = mapped_column(String(256), nullable=False)
    geometry_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="provisional", nullable=False, index=True
    )
    displacement_m: Mapped[float | None] = mapped_column(Float)
    source_sequence: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "warehouse_map_id",
            "identity_key",
            "source_sequence",
            name="uq_warehouse_layout_candidate_observation",
        ),
        CheckConstraint(
            "entity_kind IN ('aisle', 'rack', 'shelf', 'bin', 'zone', 'inspection_target')",
            name="ck_warehouse_layout_candidate_kind",
        ),
        CheckConstraint(
            "status IN ('provisional', 'needs_review', 'accepted', 'rejected')",
            name="ck_warehouse_layout_candidate_status",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_layout_candidate_confidence"
        ),
    )


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
    coordinate_frame_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_coordinate_frames.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    layout_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_layout_versions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    bin_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_bins.id", ondelete="RESTRICT"), nullable=True, index=True
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
    sensor_aim_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    shelf_normal_local_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    standoff_m: Mapped[float] = mapped_column(Float, default=1.2, nullable=False)
    hover_time_s: Mapped[float] = mapped_column(Float, default=3.0, nullable=False)
    scan_timeout_s: Mapped[float] = mapped_column(Float, default=8.0, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    provenance_status: Mapped[str] = mapped_column(
        String(24), default="manual", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    warehouse_map: Mapped[WarehouseMap] = relationship(back_populates="scan_targets")

    __table_args__ = (
        CheckConstraint(
            "provenance_status IN ('auto', 'manual', 'confirmed')",
            name="ck_warehouse_scan_target_provenance",
        ),
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
    coordinate_frame_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_coordinate_frames.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    layout_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_layout_versions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    map_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_models.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    validation_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_inspection_validation_results.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    artifact_checksums_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="planned", nullable=False, index=True)
    scan_mode: Mapped[str] = mapped_column(String(32), default="barcode", nullable=False)
    return_to_dock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    target_ids_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    plan_checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    approval_status: Mapped[str] = mapped_column(
        String(24), default="pending", nullable=False, index=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[int | None] = mapped_column(Integer)
    runtime_policy_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
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
        CheckConstraint(
            "approval_status IN ('pending', 'approved', 'rejected')",
            name="ck_warehouse_inspection_mission_approval",
        ),
    )


class WarehouseInspectionValidationResult(Base):
    __tablename__ = "warehouse_inspection_validation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_map_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_maps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    coordinate_frame_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_coordinate_frames.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    layout_version_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_layout_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    map_model_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_models.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('passed', 'failed')",
            name="ck_warehouse_inspection_validation_status",
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
