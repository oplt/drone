"""Warehouse ORM — sensor rigs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base


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


__all__ = ["WarehouseSensorRig"]
