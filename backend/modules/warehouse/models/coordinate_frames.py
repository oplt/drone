"""Warehouse ORM — coordinate frames and map setup versions."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database.base import Base

if TYPE_CHECKING:
    from .maps import WarehouseMap


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
    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
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


__all__ = ["WarehouseCoordinateFrame", "WarehouseMapSetupVersion"]
