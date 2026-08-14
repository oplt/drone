"""Warehouse ORM — scan targets and inspection missions."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database.base import Base

if TYPE_CHECKING:
    from .maps import WarehouseMap


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
    scanner_metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    path_validation_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    failure_reason: Mapped[str | None] = mapped_column(String(255))
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


__all__ = [
    "WarehouseInspectionMission",
    "WarehouseInspectionResult",
    "WarehouseInspectionValidationResult",
    "WarehouseScanTarget",
]
