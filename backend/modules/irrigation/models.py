from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database.base import Base


class CaptureRecord(Base):
    __tablename__ = "capture_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mission_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("mission_runtimes.client_flight_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    image_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    alt_m: Mapped[float | None] = mapped_column(Float)
    yaw_deg: Mapped[float | None] = mapped_column(Float)
    pitch_deg: Mapped[float | None] = mapped_column(Float)
    roll_deg: Mapped[float | None] = mapped_column(Float)
    waypoint_seq: Mapped[int | None] = mapped_column(Integer)
    frame_width: Mapped[int | None] = mapped_column(Integer)
    frame_height: Mapped[int | None] = mapped_column(Integer)
    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("idx_capture_records_mission_time", "mission_id", "timestamp_utc"),)


class ProcessedFieldLayer(Base):
    __tablename__ = "processed_field_layers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mission_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("mission_runtimes.client_flight_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    capture_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stitched_image_uri: Mapped[str | None] = mapped_column(String(2048))
    footprints_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    tile_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    bounds_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    resolution_m_per_px: Mapped[float | None] = mapped_column(Float)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IrrigationProcessingJob(Base):
    """Durable state for asynchronous field processing."""

    __tablename__ = "irrigation_processing_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mission_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("mission_runtimes.client_flight_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    requested_by_user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    force: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(128), index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnomalyZone(Base):
    __tablename__ = "anomaly_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mission_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("mission_runtimes.client_flight_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    layer_id: Mapped[int] = mapped_column(
        ForeignKey("processed_field_layers.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    area_m2: Mapped[float | None] = mapped_column(Float)
    centroid_lat: Mapped[float] = mapped_column(Float, nullable=False)
    centroid_lon: Mapped[float] = mapped_column(Float, nullable=False)
    polygon_geojson: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_image_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("idx_anomaly_zones_mission_type", "mission_id", "type"),)


class InspectionPoint(Base):
    __tablename__ = "inspection_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mission_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("mission_runtimes.client_flight_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    zone_id: Mapped[int | None] = mapped_column(
        ForeignKey("anomaly_zones.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("idx_inspection_points_mission_priority", "mission_id", "priority"),)
