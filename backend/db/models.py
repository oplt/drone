from __future__ import annotations

from datetime import datetime
from enum import Enum
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
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(32), default=FlightStatus.ACTIVE.value, nullable=False
    )
    note: Mapped[str | None] = mapped_column(String(255))
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )

    start_lat: Mapped[float] = mapped_column(Float, nullable=False)
    start_lon: Mapped[float] = mapped_column(Float, nullable=False)
    start_alt: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lat: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lon: Mapped[float] = mapped_column(Float, nullable=False)
    dest_alt: Mapped[float] = mapped_column(Float, nullable=False)

    telemetry: Mapped[list[TelemetryRecord]] = relationship(
        back_populates="flight", cascade="all, delete-orphan"
    )
    events: Mapped[list[FlightEvent]] = relationship(
        back_populates="flight", cascade="all, delete-orphan"
    )
    patrol_detections: Mapped[list[PatrolDetection]] = relationship(
        back_populates="flight", cascade="all, delete-orphan"
    )
    patrol_incidents: Mapped[list[PatrolIncident]] = relationship(
        back_populates="flight", cascade="all, delete-orphan"
    )


class FlightEvent(Base):
    __tablename__ = "flight_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flight_id: Mapped[int] = mapped_column(ForeignKey("flights.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    flight: Mapped[Flight] = relationship(back_populates="events")

    __table_args__ = (
        # optimised for flight_id + timestamp range reads
        Index("idx_flight_events_flight_time", "flight_id", "created_at"),
    )


class TelemetryRecord(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flight_id: Mapped[int | None] = mapped_column(
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
    battery_voltage: Mapped[float | None] = mapped_column(Float)
    battery_current: Mapped[float | None] = mapped_column(Float)
    battery_remaining: Mapped[float | None] = mapped_column(Float)
    system_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )

    flight: Mapped[Flight | None] = relationship(back_populates="telemetry")
    frame_id: Mapped[int | None] = mapped_column(Integer, index=True)

    __table_args__ = (
        # idempotency per flight/frame
        UniqueConstraint("flight_id", "frame_id", name="uq_telemetry_flight_frame_id"),
        # optimised for flight_id + timestamp range reads (e.g. replay, analytics)
        Index("idx_telemetry_flight_time", "flight_id", "created_at"),
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
    time_boot_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    time_unix_usec: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # Ingest-time ordering (written by _raw_event_ingest_worker)
        Index("idx_evt_flt_time", "flight_id", "created_at"),
        # Replay / audit queries filter by msg_type — covering index avoids
        # fetching the bulky JSON payload column from the heap.
        Index(
            "idx_evt_flt_type_ts",
            "flight_id",
            "msg_type",
            "timestamp",
            postgresql_include=["time_boot_ms", "time_unix_usec"],
        ),
        UniqueConstraint("flight_id", "msg_type", "time_boot_ms", name="uq_evt_flt_type_frame"),
    )


class TelemetrySummary(Base):
    """
    Pre-aggregated telemetry buckets at three resolutions (1 s, 10 s, 60 s).

    Populated by ``TelemetryRepository.build_telemetry_summaries()`` at flight
    end.  Dashboard and replay charts read from this table instead of scanning
    the raw ``telemetry`` rows.
    """

    __tablename__ = "telemetry_summary"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    flight_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("flights.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Resolution in seconds: 1, 10, or 60.
    resolution_s: Mapped[int] = mapped_column(Integer, nullable=False)
    # Start of the time bucket (UTC).
    bucket_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    avg_alt: Mapped[float | None] = mapped_column(Float)
    min_alt: Mapped[float | None] = mapped_column(Float)
    max_alt: Mapped[float | None] = mapped_column(Float)
    avg_groundspeed: Mapped[float | None] = mapped_column(Float)
    avg_battery_remaining: Mapped[float | None] = mapped_column(Float)
    min_battery_remaining: Mapped[float | None] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "flight_id",
            "resolution_s",
            "bucket_ts",
            name="uq_telsum_flt_res_bucket",
        ),
        # Primary read path: fetch all buckets for a flight at one resolution.
        Index("idx_telsum_flt_res_bucket", "flight_id", "resolution_s", "bucket_ts"),
    )


class UserRole(str, Enum):
    admin = "admin"
    org_admin = "org_admin"
    ops_manager = "ops_manager"
    pilot = "pilot"
    viewer = "viewer"
    operator = "operator"  # keep for backward compat


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", use_alter=True, name="fk_org_owner"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("org_id", "slug", name="uq_project_org_slug"),)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, name="user_role"),
        default=UserRole.operator,
        server_default="operator",
        nullable=False,
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    org: Mapped[Organization | None] = relationship(foreign_keys=[org_id])


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(String(45))

    user: Mapped[User] = relationship(back_populates="sessions")


class AuthAuditLog(Base):
    __tablename__ = "auth_audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("idx_auth_audit_user_time", "user_id", "created_at"),)


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
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (UniqueConstraint("name", name="uq_vault_secret_name"),)


class Field(Base):
    __tablename__ = "fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(
        Integer, index=True
    )  # link to users.id if you want
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # exact field border polygon (WGS84)
    boundary: Mapped[Geometry] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )

    area_ha: Mapped[float | None] = mapped_column(Float)
    centroid: Mapped[Geometry | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    models: Mapped[list[FieldModel]] = relationship(
        back_populates="field", cascade="all, delete-orphan"
    )


class FieldModel(Base):
    __tablename__ = "field_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending"
    )  # pending|processing|ready|failed

    # data quality
    gsd_cm: Mapped[float | None] = mapped_column(Float)
    epsg: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    field: Mapped[Field] = relationship(back_populates="models")
    jobs: Mapped[list[MappingJob]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )
    assets: Mapped[list[Asset]] = relationship(back_populates="model", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("field_id", "version", name="uq_field_model_version"),
        Index("idx_field_model_status", "status"),
    )


class MappingJob(Base):
    __tablename__ = "mapping_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("field_models.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending"
    )  # pending|uploading|processing|ready|failed
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # external processor (WebODM task id etc.)
    processor: Mapped[str] = mapped_column(String(32), nullable=False, default="webodm")
    processor_task_id: Mapped[str | None] = mapped_column(String(64), index=True)

    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    model: Mapped[FieldModel] = relationship(back_populates="jobs")

    __table_args__ = (Index("idx_mapping_job_status", "status"),)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("field_models.id", ondelete="CASCADE"), index=True
    )

    type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # ORTHO_COG, DSM_COG, DTM_COG, TILESET_3D, POINTCLOUD, ...
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum: Mapped[str | None] = mapped_column(String(128))

    # bbox for quick camera framing
    bbox: Mapped[Geometry | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=True,
    )

    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    model: Mapped[FieldModel] = relationship(back_populates="assets")

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
    height_m: Mapped[float | None] = mapped_column(Float)
    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Herd(Base):
    __tablename__ = "herds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # Optional: link herd to a pasture geofence you already manage
    pasture_geofence_id: Mapped[int | None] = mapped_column(
        ForeignKey("geofences.id", ondelete="SET NULL"), index=True
    )

    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    animals: Mapped[list[Animal]] = relationship(
        back_populates="herd", cascade="all, delete-orphan"
    )


class Animal(Base):
    __tablename__ = "animals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    herd_id: Mapped[int] = mapped_column(ForeignKey("herds.id", ondelete="CASCADE"), index=True)

    # Collar identity (unique)
    collar_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    name: Mapped[str | None] = mapped_column(String(128))
    species: Mapped[str] = mapped_column(
        String(32), default="cow", nullable=False
    )  # cow/sheep/goat
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    herd: Mapped[Herd] = relationship(back_populates="animals")
    positions: Mapped[list[AnimalPosition]] = relationship(
        back_populates="animal", cascade="all, delete-orphan"
    )


class AnimalPosition(Base):
    """
    Time-series positions from collars.
    Use SRID 4326 point + lat/lon columns for convenience.
    """

    __tablename__ = "animal_positions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    animal_id: Mapped[int] = mapped_column(ForeignKey("animals.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    alt: Mapped[float | None] = mapped_column(Float)

    # Optional: collar derived speed/activity
    speed_mps: Mapped[float | None] = mapped_column(Float)
    activity: Mapped[float | None] = mapped_column(Float)

    # Geo point for PostGIS queries (distance, within pasture)
    point: Mapped[Geometry] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )

    source: Mapped[str] = mapped_column(String(32), default="collar", nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    animal: Mapped[Animal] = relationship(back_populates="positions")

    __table_args__ = (Index("idx_animal_pos_animal_time", "animal_id", "created_at"),)


class HerdTask(Base):
    """
    “Task” is your domain object: census, herd sweep, search & locate, predator scan, etc.
    This lets the Livestock page show a task list and statuses.
    """

    __tablename__ = "herd_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    herd_id: Mapped[int] = mapped_column(ForeignKey("herds.id", ondelete="CASCADE"), index=True)

    type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # e.g. "census", "search_locate", "herd_sweep"
    status: Mapped[str] = mapped_column(
        String(32), default="created", nullable=False
    )  # created/running/completed/failed

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # optional link to your flights table if a drone mission is executed
    flight_id: Mapped[int | None] = mapped_column(
        ForeignKey("flights.id", ondelete="SET NULL"), index=True
    )

    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class OperationalAlert(Base):
    __tablename__ = "operational_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    rule_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="drone", nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True, nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    first_triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    occurrences: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    deliveries: Mapped[list[AlertDelivery]] = relationship(
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
    destination: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(128))
    error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    alert: Mapped[OperationalAlert] = relationship(back_populates="deliveries")


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
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=True,
    )
    area_m2: Mapped[float | None] = mapped_column(Float)
    centroid: Mapped[Geometry | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
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
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    warehouse_map: Mapped[WarehouseMap] = relationship(back_populates="docks")

    __table_args__ = (
        UniqueConstraint("warehouse_map_id", "name", name="uq_warehouse_dock_station_name"),
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
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=True,
    )
    meta_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    model: Mapped[WarehouseModel] = relationship(back_populates="assets")

    __table_args__ = (Index("idx_warehouse_asset_model_type", "model_id", "type"),)


# ---------------------------------------------------------------------------
# Mission runtime persistence
# ---------------------------------------------------------------------------


class MissionRuntime(Base):
    """Durable record of a single mission execution.

    Replaces the in-memory ``MissionRuntimeRecord`` / ``MissionRuntimeStore``
    so that mission state survives process restarts, supports operator handoff,
    and provides the anchor for replay and resume workflows.

    Lifecycle states mirror ``MissionLifecycleState``:
      queued → running → (paused ↔ running) → completed | aborted | failed
    """

    __tablename__ = "mission_runtimes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Natural key used throughout the runtime (UUID generated by the API layer).
    client_flight_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )

    # Operator who launched the mission (nullable: system-initiated missions).
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # Link to the Flight record (created once the vehicle is armed / flight starts).
    flight_id: Mapped[int | None] = mapped_column(
        ForeignKey("flights.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # Link to the preflight run that cleared this mission (nullable: skipped preflight).
    preflight_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("preflight_runs.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # --- Mission identity ---
    mission_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mission_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Sub-type used by patrol / warehouse / animal-farm missions.
    mission_task_type: Mapped[str | None] = mapped_column(String(64), index=True)
    # Further sub-type distinguishing private-patrol modes (e.g. "perimeter").
    private_patrol_task_type: Mapped[str | None] = mapped_column(String(64))
    # JSON array of AI task names active during this mission (e.g. ["person_detect"]).
    ai_tasks: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)

    # String UUID of the preflight run that cleared this mission — stored directly
    # so handlers can read it without a join (matches PreflightRun.run_uuid).
    preflight_run_uuid: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Idempotency cache for operator commands: maps idempotency_key → response dict.
    idempotency_results: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # --- Lifecycle ---
    # One of: queued | running | paused | aborted | completed | failed
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # Set when the vehicle becomes airborne (first "running" transition).
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set on terminal state (completed / aborted / failed).
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Human-readable reason for failure or abort.
    failure_reason: Mapped[str | None] = mapped_column(Text)
    # Free-form operator note (handoff notes, shift comments, etc.).
    operator_note: Mapped[str | None] = mapped_column(Text)

    # --- Resume support ---
    # Opaque JSON blob written by the mission executor as it progresses.
    # Schema is mission-type-specific; examples:
    #   GridMission:       {"completed_segment_indices": [0,1,2], "last_safe_wp": 7}
    #   WaypointsMission:  {"last_completed_wp_index": 4}
    #   PrivatePatrol:     {"last_completed_checkpoint": "cp-3"}
    resume_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Original mission parameters snapshot (polygon, altitude, speed, overlap, …).
    # Stored so a resumed or re-run mission uses identical parameters.
    mission_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Ordered audit trail of operator commands (pause, resume, RTH, abort, …).
    # Each entry matches the shape of MissionCommandAuditRecord.
    command_audit: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)

    # --- Relationships ---
    user: Mapped[User | None] = relationship(foreign_keys=[user_id])
    flight: Mapped[Flight | None] = relationship(foreign_keys=[flight_id])
    preflight_run: Mapped[PreflightRun | None] = relationship(
        back_populates="mission_runtime", foreign_keys=[preflight_run_id]
    )

    __table_args__ = (
        Index("idx_mission_runtime_state_created", "state", "created_at"),
        Index("idx_mission_runtime_user", "user_id", "created_at"),
    )


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
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
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

    __table_args__ = (
        Index("idx_capture_records_mission_time", "mission_id", "timestamp_utc"),
    )


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

    __table_args__ = (
        Index("idx_anomaly_zones_mission_type", "mission_id", "type"),
    )


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

    __table_args__ = (
        Index("idx_inspection_points_mission_priority", "mission_id", "priority"),
    )


class PreflightRun(Base):
    """Persistent record of a single preflight check execution.

    Replaces ad-hoc ``preflight_report`` FlightEvent rows with a first-class
    table so results are structured, queryable, and linkable to a
    ``MissionRuntime``.
    """

    __tablename__ = "preflight_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # UUID assigned at run start; matches the ``preflight_run_id`` stored in
    # ``MissionRuntimeRecord`` and ``MissionRuntime``.
    run_uuid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # Optional link to the flight record if one already exists at preflight time.
    flight_id: Mapped[int | None] = mapped_column(
        ForeignKey("flights.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # Operator who triggered the preflight (nullable: automated runs).
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )

    # --- Mission context ---
    mission_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mission_name: Mapped[str | None] = mapped_column(String(255))

    # SHA-256 of the mission payload at the time of preflight — used to validate
    # that the mission launched matches the payload that was preflight-checked.
    mission_fingerprint: Mapped[str | None] = mapped_column(String(64))

    # Wall-clock expiry — preflight tokens are only valid for PREFLIGHT_RUN_TTL_SECONDS.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Vehicle identifier reported by the drone at preflight time.
    vehicle_id: Mapped[str | None] = mapped_column(String(64))

    # --- Result ---
    # One of: PASS | WARN | FAIL
    overall_status: Mapped[str] = mapped_column(String(8), nullable=False, index=True)

    # Structured check results — matches PreflightReport.base_checks / mission_checks.
    # Each item: {"name": str, "status": str, "message": str|null}
    base_checks: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    mission_checks: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)

    # Names of checks with status FAIL that blocked launch.
    critical_failures: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)

    # Aggregated counts: {passed, warned, failed, skipped}
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Whether the operator explicitly acknowledged warnings and proceeded.
    operator_acknowledged_warnings: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # --- Timestamps ---
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # --- Relationships ---
    mission_runtime: Mapped[MissionRuntime | None] = relationship(
        back_populates="preflight_run",
        foreign_keys="MissionRuntime.preflight_run_id",
    )

    __table_args__ = (
        Index("idx_preflight_run_status_created", "overall_status", "created_at"),
        Index("idx_preflight_run_flight", "flight_id"),
    )


class OperatorCommand(Base):
    """Explicit, queryable record of every operator command issued against a mission.

    Complements the denormalised ``MissionRuntime.command_audit`` JSON column
    with a first-class table so commands can be queried, audited, and indexed
    independently of the runtime row.

    Supported commands: pause | resume | abort | rth | land
    """

    __tablename__ = "operator_commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Natural key generated by the API layer: "cmd_{ts}_{hex}".
    command_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # FK to the owning mission runtime (set NULL on runtime delete for audit preservation).
    mission_runtime_id: Mapped[int | None] = mapped_column(
        ForeignKey("mission_runtimes.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # Denormalised so commands remain readable even if the runtime row is deleted.
    client_flight_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # --- Command payload ---
    command: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # State snapshot at the moment the command was evaluated.
    state_before: Mapped[str] = mapped_column(String(32), nullable=False)
    state_after: Mapped[str] = mapped_column(String(32), nullable=False)

    # Whether the command was accepted and the drone call succeeded.
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Human-readable outcome message.
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Optional operator-provided reason.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # --- Relationship ---
    mission_runtime: Mapped[MissionRuntime | None] = relationship(foreign_keys=[mission_runtime_id])

    __table_args__ = (
        Index("idx_operator_command_runtime", "mission_runtime_id", "requested_at"),
        Index("idx_operator_command_flight", "client_flight_id", "requested_at"),
    )


class ExportJob(Base):
    __tablename__ = "export_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )
    flight_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    download_url: Mapped[str | None] = mapped_column(String(2048))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(512))


# ---------------------------------------------------------------------------
# P3 — Platform & Growth models
# ---------------------------------------------------------------------------


class MissionTemplate(Base):
    """Saved mission configuration for one-click rerun and scheduled dispatch."""

    __tablename__ = "mission_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    mission_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    preflight_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    schedule_cron: Mapped[str | None] = mapped_column(String(64))  # cron expression; None = manual only
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    runs: Mapped[list[ScheduledRun]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_mission_template_org_slug"),
        Index("idx_mission_template_org_active", "org_id", "is_active"),
    )


class ScheduledRun(Base):
    """Record of each execution of a MissionTemplate (scheduled or manual)."""

    __tablename__ = "scheduled_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("mission_templates.id", ondelete="CASCADE"), index=True, nullable=False
    )
    triggered_by: Mapped[str] = mapped_column(String(16), nullable=False)  # "schedule" | "manual"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    template: Mapped[MissionTemplate] = relationship(back_populates="runs")

    __table_args__ = (Index("idx_scheduled_run_template_time", "template_id", "created_at"),)


class ApiKey(Base):
    """Permission-scoped API key for external integrations and public API access."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 of raw secret
    scopes: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("idx_api_key_org_revoked", "org_id", "revoked"),)


class WebhookEndpoint(Base):
    """Outbound webhook subscription for org-scoped event delivery."""

    __tablename__ = "webhook_endpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    events: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    secret: Mapped[str] = mapped_column(String(64), nullable=False)  # HMAC signing key
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    deliveries: Mapped[list[WebhookDelivery]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_webhook_endpoint_org_active", "org_id", "is_active"),)


class WebhookDelivery(Base):
    """Individual webhook delivery attempt with retry tracking."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_code: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    endpoint: Mapped[WebhookEndpoint] = relationship(back_populates="deliveries")

    __table_args__ = (
        Index("idx_webhook_delivery_endpoint_time", "endpoint_id", "created_at"),
        Index("idx_webhook_delivery_status_retry", "status", "next_retry_at"),
    )


class FieldDeliverable(Base):
    """Generated agronomy deliverable (GeoJSON, HTML summary, KML) with public share link."""

    __tablename__ = "field_deliverables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(
        ForeignKey("fields.id", ondelete="CASCADE"), index=True, nullable=False
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # QA_CHECKLIST | HTML_SUMMARY | GEOJSON | KML
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    url: Mapped[str | None] = mapped_column(String(2048))  # S3 key or local path
    share_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("idx_field_deliverable_field_type", "field_id", "type"),)


class ComplianceRecord(Base):
    """FAA / LAANC compliance metadata for a mission runtime."""

    __tablename__ = "compliance_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    mission_runtime_id: Mapped[int] = mapped_column(
        ForeignKey("mission_runtimes.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    remote_id_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown"
    )  # broadcast | off | unknown
    laanc_auth_number: Mapped[str | None] = mapped_column(String(64))
    laanc_auth_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preflight_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OperatorCertification(Base):
    """Regulatory certification held by a drone operator (FAA Part 107, etc.)."""

    __tablename__ = "operator_certifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    cert_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # FAA_PART_107 | ICAO_RPAS | OTHER
    cert_number: Mapped[str] = mapped_column(String(128), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issuing_authority: Mapped[str | None] = mapped_column(String(255))
    document_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("idx_operator_cert_user_type", "user_id", "cert_type"),)


class DeviceReadiness(Base):
    """Per-device airworthiness and inspection tracking."""

    __tablename__ = "device_readiness"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    device_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_inspection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_inspection_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="airworthy"
    )  # airworthy | grounded | limited
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("device_id", "org_id", name="uq_device_readiness_device_org"),
        Index("idx_device_readiness_org_status", "org_id", "status"),
    )
