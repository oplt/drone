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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database.base import Base


class PropertyPatrolSite(Base):
    __tablename__ = "property_patrol_sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    property_boundary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    flight_safe_area: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    no_fly_zones: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    privacy_zones: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    emergency_landing_zones: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    default_home_position: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    default_altitude_m: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    templates: Mapped[list[PropertyPatrolTemplate]] = relationship(back_populates="site", cascade="all, delete-orphan")
    runs: Mapped[list[PropertyPatrolRun]] = relationship(back_populates="site")


class PropertyPatrolTemplate(Base):
    __tablename__ = "property_patrol_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("property_patrol_sites.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    patrol_mode: Mapped[str] = mapped_column(String(24), default="perimeter", nullable=False)
    altitude_m: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    speed_mps: Mapped[float] = mapped_column(Float, default=6.0, nullable=False)
    boundary_offset_m: Mapped[float] = mapped_column(Float, default=15.0, nullable=False)
    grid_spacing_m: Mapped[float] = mapped_column(Float, default=40.0, nullable=False)
    overlap_percent: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)
    camera_direction: Mapped[str] = mapped_column(String(24), default="inward", nullable=False)
    camera_gimbal_pitch_deg: Mapped[float] = mapped_column(Float, default=35.0, nullable=False)
    schedule_interval_minutes: Mapped[int | None] = mapped_column(Integer)
    max_mission_duration_minutes: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    min_battery_return_percent: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    trigger_behavior: Mapped[str] = mapped_column(String(24), default="approval_required", nullable=False)
    ai_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    llm_summary_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    privacy_blur_faces: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    privacy_blur_license_plates: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    event_clip_recording_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    retention_hours_or_days: Mapped[str] = mapped_column(String(32), default="72h", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    site: Mapped[PropertyPatrolSite] = relationship(back_populates="templates")
    runs: Mapped[list[PropertyPatrolRun]] = relationship(back_populates="template")


class PropertyPatrolRun(Base):
    __tablename__ = "property_patrol_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("property_patrol_templates.id", ondelete="SET NULL"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("property_patrol_sites.id", ondelete="CASCADE"), index=True)
    mission_type: Mapped[str] = mapped_column(String(24), default="manual", nullable=False)
    state: Mapped[str] = mapped_column(String(40), default="DRAFT", nullable=False, index=True)
    route_waypoints: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    drone_id: Mapped[str | None] = mapped_column(String(128))
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    site: Mapped[PropertyPatrolSite] = relationship(back_populates="runs")
    template: Mapped[PropertyPatrolTemplate | None] = relationship(back_populates="runs")


class PropertyPatrolSensorEvent(Base):
    __tablename__ = "property_patrol_sensor_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    sensor_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("property_patrol_sites.id", ondelete="CASCADE"), index=True)
    zone_id: Mapped[str | None] = mapped_column(String(160), index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    approx_location: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    evidence_clip_id: Mapped[str | None] = mapped_column(String(255))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="received", nullable=False, index=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("site_id", "external_event_id", name="uq_property_patrol_event_site_external"),)


class PropertyPatrolIncident(Base):
    __tablename__ = "property_patrol_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("property_patrol_sites.id", ondelete="CASCADE"), index=True)
    mission_run_id: Mapped[int | None] = mapped_column(ForeignKey("property_patrol_runs.id", ondelete="SET NULL"), index=True)
    sensor_event_id: Mapped[int | None] = mapped_column(ForeignKey("property_patrol_sensor_events.id", ondelete="SET NULL"), index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(24), default="medium", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    zone_id: Mapped[str | None] = mapped_column(String(160), index=True)
    detected_objects: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    video_clip_id: Mapped[str | None] = mapped_column(String(255))
    snapshot_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    llm_summary: Mapped[str | None] = mapped_column(Text)
    operator_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (Index("idx_property_patrol_incident_site_status", "site_id", "status"),)

