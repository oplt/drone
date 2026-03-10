from __future__ import annotations
from datetime import datetime
from enum import Enum
from geoalchemy2 import Geometry
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import (
    String,
    Integer,
    Float,
    DateTime,
    ForeignKey,
    JSON,
    func,
    UniqueConstraint,
    BigInteger,
    Index,
    Boolean,
    LargeBinary,
    Text,
)



class Base(DeclarativeBase):
    pass


class FlightStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"

    @classmethod
    def terminal_values(cls) -> set[str]:
        return {cls.COMPLETED.value, cls.INTERRUPTED.value, cls.FAILED.value}


_FLIGHT_STATUS_ALIASES: dict[str, FlightStatus] = {
    "running": FlightStatus.ACTIVE,
    "in_progress": FlightStatus.ACTIVE,
    "aborted": FlightStatus.INTERRUPTED,
}


def normalize_flight_status(status: str | FlightStatus) -> FlightStatus:
    if isinstance(status, FlightStatus):
        return status
    raw = str(status).strip().lower()
    if not raw:
        raise ValueError("Flight status cannot be empty")
    aliased = _FLIGHT_STATUS_ALIASES.get(raw)
    if aliased is not None:
        return aliased
    try:
        return FlightStatus(raw)
    except ValueError as exc:
        allowed = ", ".join(s.value for s in FlightStatus)
        raise ValueError(f"Unsupported flight status '{status}'. Allowed: {allowed}") from exc


class Flight(Base):
    __tablename__ = "flights"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(32), default=FlightStatus.ACTIVE.value, nullable=False
    )
    note: Mapped[Optional[str]] = mapped_column(String(255))

    start_lat: Mapped[float] = mapped_column(Float, nullable=False)
    start_lon: Mapped[float] = mapped_column(Float, nullable=False)
    start_alt: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lat: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lon: Mapped[float] = mapped_column(Float, nullable=False)
    dest_alt: Mapped[float] = mapped_column(Float, nullable=False)

    telemetry: Mapped[list["TelemetryRecord"]] = relationship(
        back_populates="flight", cascade="all, delete-orphan"
    )
    events: Mapped[list["FlightEvent"]] = relationship(
        back_populates="flight", cascade="all, delete-orphan"
    )
    patrol_detections: Mapped[list["PatrolDetection"]] = relationship(
        back_populates="flight", cascade="all, delete-orphan"
    )
    patrol_incidents: Mapped[list["PatrolIncident"]] = relationship(
        back_populates="flight", cascade="all, delete-orphan"
    )


class FlightEvent(Base):
    __tablename__ = "flight_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flight_id: Mapped[int] = mapped_column(
        ForeignKey("flights.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    flight: Mapped["Flight"] = relationship(back_populates="events")


class TelemetryRecord(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flight_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("flights.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    alt: Mapped[float] = mapped_column(Float, nullable=False)
    heading: Mapped[float] = mapped_column(Float, nullable=False)
    groundspeed: Mapped[float] = mapped_column(Float, nullable=False)
    # armed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    battery_voltage: Mapped[Optional[float]] = mapped_column(Float)
    battery_current: Mapped[Optional[float]] = mapped_column(Float)
    battery_remaining: Mapped[Optional[float]] = mapped_column(Float)
    system_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )

    flight: Mapped[Optional["Flight"]] = relationship(back_populates="telemetry")
    frame_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)

    __table_args__ = (
        # idempotency per flight/frame
        UniqueConstraint("flight_id", "frame_id", name="uq_telemetry_flight_frame_id"),
    )


class MavlinkEvent(Base):
    __tablename__ = "mavlink_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    flight_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    msg_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # sysid: Mapped[Optional[int]] = mapped_column(Integer)
    # compid: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSON)
    # Boot time in milliseconds since vehicle boot (not a UTC timestamp).
    time_boot_ms: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True
    )
    time_unix_usec: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("idx_evt_flt_time", "flight_id", "created_at"),
        UniqueConstraint(
            "flight_id", "msg_type", "time_boot_ms", name="uq_evt_flt_type_frame"
        ),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Geofence(Base):
    __tablename__ = "geofences"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)

    # GeoAlchemy2 integration with Mapped
    polygon: Mapped[Geometry] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )

    min_alt_m: Mapped[float | None] = mapped_column(Float)
    max_alt_m: Mapped[float | None] = mapped_column(Float)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # This was the specific line causing your error:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())




class SettingsRow(Base):
    """
    Single-row settings document (id=1), non-secret config only.
    Secrets are stored in VaultSecret.
    """
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class VaultSecret(Base):
    """
    Encrypted-at-rest secrets store.
    - name: unique key (e.g. "llm_api_key", "mqtt_pass")
    - ciphertext: encrypted bytes (Fernet/AESGCM, etc.)
    """
    __tablename__ = "vault_secrets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("name", name="uq_vault_secret_name"),)



class Field(Base):
    __tablename__ = "fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)  # link to users.id if you want
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # exact field border polygon (WGS84)
    boundary: Mapped[Geometry] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )

    area_ha: Mapped[Optional[float]] = mapped_column(Float)
    centroid: Mapped[Optional[Geometry]] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    models: Mapped[list["FieldModel"]] = relationship(back_populates="field", cascade="all, delete-orphan")


class FieldModel(Base):
    __tablename__ = "field_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")  # pending|processing|ready|failed

    # data quality
    gsd_cm: Mapped[Optional[float]] = mapped_column(Float)
    epsg: Mapped[Optional[int]] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    field: Mapped["Field"] = relationship(back_populates="models")
    jobs: Mapped[list["MappingJob"]] = relationship(back_populates="model", cascade="all, delete-orphan")
    assets: Mapped[list["Asset"]] = relationship(back_populates="model", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("field_id", "version", name="uq_field_model_version"),
        Index("idx_field_model_status", "status"),
    )


class MappingJob(Base):
    __tablename__ = "mapping_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("field_models.id", ondelete="CASCADE"), index=True)

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")  # pending|uploading|processing|ready|failed
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # external processor (WebODM task id etc.)
    processor: Mapped[str] = mapped_column(String(32), nullable=False, default="webodm")
    processor_task_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    params: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    model: Mapped["FieldModel"] = relationship(back_populates="jobs")

    __table_args__ = (Index("idx_mapping_job_status", "status"),)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("field_models.id", ondelete="CASCADE"), index=True)

    type: Mapped[str] = mapped_column(String(32), nullable=False)  # ORTHO_COG, DSM_COG, DTM_COG, TILESET_3D, POINTCLOUD, ...
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    checksum: Mapped[Optional[str]] = mapped_column(String(128))

    # bbox for quick camera framing
    bbox: Mapped[Optional[Geometry]] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=True,
    )

    meta_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    model: Mapped["FieldModel"] = relationship(back_populates="assets")

    __table_args__ = (Index("idx_asset_model_type", "model_id", "type"),)


class Obstacle(Base):
    """
    Operator-annotated or imported obstacles (trees, poles, buildings) to mask routes.
    Use POINT for simple obstacles; you can add POLYGON later.
    """
    __tablename__ = "obstacles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    location: Mapped[Geometry] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )
    radius_m: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    height_m: Mapped[Optional[float]] = mapped_column(Float)
    meta_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# backend/db/models.py  (APPEND)

from geoalchemy2 import Geometry
from sqlalchemy import Text

class Herd(Base):
    __tablename__ = "herds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # Optional: link herd to a pasture geofence you already manage
    pasture_geofence_id: Mapped[Optional[int]] = mapped_column(ForeignKey("geofences.id", ondelete="SET NULL"), index=True)

    meta_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    animals: Mapped[List["Animal"]] = relationship(back_populates="herd", cascade="all, delete-orphan")


class Animal(Base):
    __tablename__ = "animals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    herd_id: Mapped[int] = mapped_column(ForeignKey("herds.id", ondelete="CASCADE"), index=True)

    # Collar identity (unique)
    collar_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    name: Mapped[Optional[str]] = mapped_column(String(128))
    species: Mapped[str] = mapped_column(String(32), default="cow", nullable=False)  # cow/sheep/goat
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    meta_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    herd: Mapped["Herd"] = relationship(back_populates="animals")
    positions: Mapped[List["AnimalPosition"]] = relationship(back_populates="animal", cascade="all, delete-orphan")


class AnimalPosition(Base):
    """
    Time-series positions from collars.
    Use SRID 4326 point + lat/lon columns for convenience.
    """
    __tablename__ = "animal_positions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    animal_id: Mapped[int] = mapped_column(ForeignKey("animals.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    alt: Mapped[Optional[float]] = mapped_column(Float)

    # Optional: collar derived speed/activity
    speed_mps: Mapped[Optional[float]] = mapped_column(Float)
    activity: Mapped[Optional[float]] = mapped_column(Float)

    # Geo point for PostGIS queries (distance, within pasture)
    point: Mapped[Geometry] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )

    source: Mapped[str] = mapped_column(String(32), default="collar", nullable=False)
    raw: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    animal: Mapped["Animal"] = relationship(back_populates="positions")

    __table_args__ = (
        Index("idx_animal_pos_animal_time", "animal_id", "created_at"),
    )


class HerdTask(Base):
    """
    “Task” is your domain object: census, herd sweep, search & locate, predator scan, etc.
    This lets the Livestock page show a task list and statuses.
    """
    __tablename__ = "herd_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    herd_id: Mapped[int] = mapped_column(ForeignKey("herds.id", ondelete="CASCADE"), index=True)

    type: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "census", "search_locate", "herd_sweep"
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)  # created/running/completed/failed

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # optional link to your flights table if a drone mission is executed
    flight_id: Mapped[Optional[int]] = mapped_column(ForeignKey("flights.id", ondelete="SET NULL"), index=True)

    params: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class OperationalAlert(Base):
    __tablename__ = "operational_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="drone", nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True, nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    meta_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    first_triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    acknowledged_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    occurrences: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    deliveries: Mapped[List["AlertDelivery"]] = relationship(
        back_populates="alert",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_operational_alert_status_triggered", "status", "last_triggered_at"),
        Index("idx_operational_alert_rule_status", "rule_type", "status"),
    )


class AlertDelivery(Base):
    __tablename__ = "alert_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("operational_alerts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    destination: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(128))
    error: Mapped[Optional[str]] = mapped_column(Text)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    alert: Mapped["OperationalAlert"] = relationship(back_populates="deliveries")


class PatrolDetection(Base):
    __tablename__ = "patrol_detections"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    flight_id: Mapped[int] = mapped_column(
        ForeignKey("flights.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    telemetry_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("telemetry.id", ondelete="SET NULL"),
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    frame_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)

    mission_task_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    ai_task: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    object_class: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    anomaly_type: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    track_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    zone_name: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    checkpoint_index: Mapped[Optional[int]] = mapped_column(Integer, index=True)

    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    bbox_xyxy: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    centroid_xy: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    alt: Mapped[Optional[float]] = mapped_column(Float)

    heading: Mapped[Optional[float]] = mapped_column(Float)
    groundspeed: Mapped[Optional[float]] = mapped_column(Float)

    source: Mapped[str] = mapped_column(String(32), default="rgb", nullable=False)
    snapshot_path: Mapped[Optional[str]] = mapped_column(String(1024))
    clip_path: Mapped[Optional[str]] = mapped_column(String(1024))

    model_name: Mapped[Optional[str]] = mapped_column(String(128))
    model_version: Mapped[Optional[str]] = mapped_column(String(64))

    meta_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    flight: Mapped["Flight"] = relationship(back_populates="patrol_detections")
    telemetry: Mapped[Optional["TelemetryRecord"]] = relationship()
    incident_links: Mapped[List["PatrolIncidentDetection"]] = relationship(
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
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(32), default="open", index=True, nullable=False)

    mission_task_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    incident_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    primary_object_class: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    primary_track_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    ai_task: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    zone_name: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    checkpoint_index: Mapped[Optional[int]] = mapped_column(Integer, index=True)

    start_lat: Mapped[Optional[float]] = mapped_column(Float)
    start_lon: Mapped[Optional[float]] = mapped_column(Float)
    end_lat: Mapped[Optional[float]] = mapped_column(Float)
    end_lon: Mapped[Optional[float]] = mapped_column(Float)

    peak_confidence: Mapped[Optional[float]] = mapped_column(Float)
    detection_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    first_detection_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)
    last_detection_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)

    snapshot_path: Mapped[Optional[str]] = mapped_column(String(1024))
    clip_path: Mapped[Optional[str]] = mapped_column(String(1024))

    last_alert_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("operational_alerts.id", ondelete="SET NULL"),
        index=True,
    )

    summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    flight: Mapped["Flight"] = relationship(back_populates="patrol_incidents")
    detection_links: Mapped[List["PatrolIncidentDetection"]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
    )
    last_alert: Mapped[Optional["OperationalAlert"]] = relationship()

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

    incident: Mapped["PatrolIncident"] = relationship(back_populates="detection_links")
    detection: Mapped["PatrolDetection"] = relationship(back_populates="incident_links")