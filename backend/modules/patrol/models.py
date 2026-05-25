from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database.base import Base

if TYPE_CHECKING:
    from backend.modules.alerts.models import OperationalAlert
    from backend.modules.missions.flight_models import Flight
    from backend.modules.telemetry.models import TelemetryRecord


class PatrolDetection(Base):
    __tablename__ = "patrol_detections"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    flight_id: Mapped[int] = mapped_column(
        ForeignKey("flights.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    telemetry_id: Mapped[int | None] = mapped_column(
        ForeignKey("telemetry.id", ondelete="SET NULL"),
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    frame_id: Mapped[int | None] = mapped_column(Integer, index=True)

    mission_task_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    ai_task: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    object_class: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    anomaly_type: Mapped[str | None] = mapped_column(String(64), index=True)
    track_id: Mapped[str | None] = mapped_column(String(64), index=True)

    zone_name: Mapped[str | None] = mapped_column(String(128), index=True)
    checkpoint_index: Mapped[int | None] = mapped_column(Integer, index=True)

    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    bbox_xyxy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    centroid_xy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    alt: Mapped[float | None] = mapped_column(Float)

    heading: Mapped[float | None] = mapped_column(Float)
    groundspeed: Mapped[float | None] = mapped_column(Float)

    source: Mapped[str] = mapped_column(String(32), default="rgb", nullable=False)
    snapshot_path: Mapped[str | None] = mapped_column(String(1024))
    clip_path: Mapped[str | None] = mapped_column(String(1024))

    model_name: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(64))

    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    flight: Mapped[Flight] = relationship(back_populates="patrol_detections")
    telemetry: Mapped[TelemetryRecord | None] = relationship()
    incident_links: Mapped[list[PatrolIncidentDetection]] = relationship(
        back_populates="detection",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_patrol_det_flight_time", "flight_id", "created_at"),
        Index("idx_patrol_det_flight_track", "flight_id", "track_id"),
        Index("idx_patrol_det_task_ai", "mission_task_type", "ai_task"),
        Index("idx_patrol_det_object_anomaly", "object_class", "anomaly_type"),
    )


class PatrolIncident(Base):
    __tablename__ = "patrol_incidents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    flight_id: Mapped[int] = mapped_column(
        ForeignKey("flights.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(32), default="open", index=True, nullable=False)

    mission_task_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    incident_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    primary_object_class: Mapped[str | None] = mapped_column(String(64), index=True)
    primary_track_id: Mapped[str | None] = mapped_column(String(64), index=True)

    ai_task: Mapped[str | None] = mapped_column(String(64), index=True)

    zone_name: Mapped[str | None] = mapped_column(String(128), index=True)
    checkpoint_index: Mapped[int | None] = mapped_column(Integer, index=True)

    start_lat: Mapped[float | None] = mapped_column(Float)
    start_lon: Mapped[float | None] = mapped_column(Float)
    end_lat: Mapped[float | None] = mapped_column(Float)
    end_lon: Mapped[float | None] = mapped_column(Float)

    peak_confidence: Mapped[float | None] = mapped_column(Float)
    detection_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    first_detection_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    last_detection_id: Mapped[int | None] = mapped_column(BigInteger, index=True)

    snapshot_path: Mapped[str | None] = mapped_column(String(1024))
    clip_path: Mapped[str | None] = mapped_column(String(1024))

    last_alert_id: Mapped[int | None] = mapped_column(
        ForeignKey("operational_alerts.id", ondelete="SET NULL"),
        index=True,
    )

    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    flight: Mapped[Flight] = relationship(back_populates="patrol_incidents")
    detection_links: Mapped[list[PatrolIncidentDetection]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
    )
    last_alert: Mapped[OperationalAlert | None] = relationship()

    __table_args__ = (
        Index("idx_patrol_inc_flight_opened", "flight_id", "opened_at"),
        Index("idx_patrol_inc_type_status", "incident_type", "status"),
        Index("idx_patrol_inc_track_status", "primary_track_id", "status"),
    )


class PatrolIncidentDetection(Base):
    __tablename__ = "patrol_incident_detections"

    incident_id: Mapped[int] = mapped_column(
        ForeignKey("patrol_incidents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    detection_id: Mapped[int] = mapped_column(
        ForeignKey("patrol_detections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    incident: Mapped[PatrolIncident] = relationship(back_populates="detection_links")
    detection: Mapped[PatrolDetection] = relationship(back_populates="incident_links")
