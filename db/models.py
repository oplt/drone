from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    func,
    UniqueConstraint,
    BigInteger,
    Index,
    select,
)
from itsdangerous import URLSafeTimedSerializer as Serializer
from flask_login import UserMixin

# Note: Session imported inside functions to avoid circular import with db.session


class Base(DeclarativeBase):
    pass


# Sync user loader for Flask-Login (using sync database)
def load_user_sync(user_id: str) -> Optional["User"]:
    """Synchronous user loader for Flask-Login"""
    # Import here to avoid circular import
    from db.flask_session import get_sync_session
    from sqlalchemy import select

    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        return None

    with get_sync_session() as session:
        result = session.execute(select(User).where(User.id == user_id_int))
        return result.scalar_one_or_none()


class User(Base, UserMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(
        String(120), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    image_file: Mapped[str] = mapped_column(
        String(20), default="default.jpg", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    flights: Mapped[List["Flight"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_user_email_active", "email", "is_active"),
        Index("idx_user_created", "created_at"),
    )

    def set_password(self, password: str) -> None:
        """Set password hash using bcrypt"""
        from flask_app.app import bcrypt

        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password: str) -> bool:
        """Check password against hash"""
        from flask_app.app import bcrypt

        return bcrypt.check_password_hash(self.password_hash, password)

    def get_reset_token(self, expires_sec=1800):
        """Generate password reset token"""
        from flask import current_app

        s = Serializer(current_app.config["SECRET_KEY"], expires_sec)
        return s.dumps({"user_id": self.id}).decode("utf-8")

    @staticmethod
    async def verify_reset_token(token: str) -> Optional["User"]:
        """Verify and return user from reset token"""
        # Import here to avoid circular import
        from db.session import Session
        from flask import current_app

        s = Serializer(current_app.config["SECRET_KEY"])
        try:
            user_id = s.loads(token)["user_id"]
        except Exception:
            return None

        async with Session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            return result.scalar_one_or_none()

    def __repr__(self):
        return f"User('{self.username}', '{self.email}', '{self.image_file}')"


class Flight(Base):
    __tablename__ = "flights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(32), default="in_progress", nullable=False
    )
    note: Mapped[Optional[str]] = mapped_column(String(255))

    start_lat: Mapped[float] = mapped_column(Float, nullable=False)
    start_lon: Mapped[float] = mapped_column(Float, nullable=False)
    start_alt: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lat: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lon: Mapped[float] = mapped_column(Float, nullable=False)
    dest_alt: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationships
    user: Mapped[Optional["User"]] = relationship(back_populates="flights")
    telemetry: Mapped[list["TelemetryRecord"]] = relationship(
        back_populates="flight", cascade="all, delete-orphan"
    )
    events: Mapped[list["FlightEvent"]] = relationship(
        back_populates="flight", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_flight_user_status", "user_id", "status"),
        Index("idx_flight_dates", "started_at", "ended_at"),
    )


# The rest of your models (FlightEvent, TelemetryRecord, MavlinkEvent) remain the same...


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

    __table_args__ = (
        Index(
            "idx_flight_events_flight_type", "flight_id", "type"
        ),  # Fast event lookups
        Index("idx_flight_events_time", "created_at"),  # Time-based queries
    )


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
        UniqueConstraint("flight_id", "frame_id", name="uq_telemetry_flight_frame_id"),
        Index("idx_telemetry_flight_created", "flight_id", "created_at"),  # Add this
        Index("idx_telemetry_created_at", "created_at"),
        Index("idx_telemetry_coords", "lat", "lon"),
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
    # ArduPilot time since boot (milliseconds). Not a wall-clock timestamp.
    time_boot_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    time_unix_usec: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("idx_mavlink_flight_msg_time", "flight_id", "msg_type", "created_at"),
        Index("idx_mavlink_timestamp", "timestamp"),  # Add this!
        Index("idx_mavlink_type_time", "msg_type", "created_at"),  # Add this!
        UniqueConstraint(
            "flight_id", "msg_type", "time_boot_ms", name="uq_evt_flt_type_frame"
        ),
    )


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Google Maps
    google_maps_key: Mapped[Optional[str]] = mapped_column(String(512))
    google_javascript_api_key: Mapped[Optional[str]] = mapped_column(String(512))

    # LLM Settings
    llm_provider: Mapped[Optional[str]] = mapped_column(String(64))
    llm_api_base: Mapped[Optional[str]] = mapped_column(String(512))
    llm_api_key: Mapped[Optional[str]] = mapped_column(String(512))
    llm_model: Mapped[Optional[str]] = mapped_column(String(128))

    # MQTT Settings
    mqtt_broker: Mapped[Optional[str]] = mapped_column(String(256))
    mqtt_port: Mapped[Optional[int]] = mapped_column(Integer)
    mqtt_user: Mapped[Optional[str]] = mapped_column(String(128))
    mqtt_pass: Mapped[Optional[str]] = mapped_column(String(256))
    opcua_endpoint: Mapped[Optional[str]] = mapped_column(String(512))

    # Drone Connection
    drone_conn: Mapped[Optional[str]] = mapped_column(String(256))
    drone_conn_mavproxy: Mapped[Optional[str]] = mapped_column(String(256))
    drone_baud_rate: Mapped[Optional[int]] = mapped_column(Integer)

    # Telemetry
    telem_log_interval_sec: Mapped[Optional[float]] = mapped_column(Float)
    telemetry_topic: Mapped[Optional[str]] = mapped_column(String(128))

    # Video Settings
    drone_video_enabled: Mapped[Optional[bool]] = mapped_column(Boolean)
    drone_video_width: Mapped[Optional[int]] = mapped_column(Integer)
    drone_video_height: Mapped[Optional[int]] = mapped_column(Integer)
    drone_video_fps: Mapped[Optional[int]] = mapped_column(Integer)
    drone_video_timeout: Mapped[Optional[float]] = mapped_column(Float)
    drone_video_fallback: Mapped[Optional[str]] = mapped_column(String(512))
    drone_video_save_stream: Mapped[Optional[bool]] = mapped_column(Boolean)
    drone_video_save_path: Mapped[Optional[str]] = mapped_column(String(512))

    # Battery & Flight Parameters
    battery_capacity_wh: Mapped[Optional[float]] = mapped_column(Float)
    cruise_power_w: Mapped[Optional[float]] = mapped_column(Float)
    cruise_speed_mps: Mapped[Optional[float]] = mapped_column(Float)
    energy_reserve_frac: Mapped[Optional[float]] = mapped_column(Float)
    heartbeat_timeout: Mapped[Optional[float]] = mapped_column(Float)
    enforce_preflight_range: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Raspberry Pi Settings
    rasperry_ip: Mapped[Optional[str]] = mapped_column(String(128))
    rasperry_user: Mapped[Optional[str]] = mapped_column(String(128))
    rasperry_host: Mapped[Optional[str]] = mapped_column(String(256))
    rasperry_password: Mapped[Optional[str]] = mapped_column(String(256))
    rasperry_streaming_script_path: Mapped[Optional[str]] = mapped_column(String(512))
    ssh_key_path: Mapped[Optional[str]] = mapped_column(String(512))
    raspberry_camera_enabled: Mapped[Optional[bool]] = mapped_column(Boolean)
    rasperry_streaming_port: Mapped[Optional[int]] = mapped_column(Integer)

    # Database Settings
    db_pool_size: Mapped[Optional[int]] = mapped_column(Integer)
    db_max_overflow: Mapped[Optional[int]] = mapped_column(Integer)
    db_pool_recycle: Mapped[Optional[int]] = mapped_column(Integer)
    db_pool_timeout: Mapped[Optional[int]] = mapped_column(Integer)
    db_pool_pre_ping: Mapped[Optional[bool]] = mapped_column(Boolean)
    db_echo: Mapped[Optional[bool]] = mapped_column(Boolean)
    database_url: Mapped[Optional[str]] = mapped_column(String(512))
    db_optimize_interval: Mapped[Optional[int]] = mapped_column(Integer)

    # Flask Settings
    flask_secret_key: Mapped[Optional[str]] = mapped_column(String(256))
    mail_server: Mapped[Optional[str]] = mapped_column(String(256))
    mail_port: Mapped[Optional[int]] = mapped_column(Integer)
    mail_use_tls: Mapped[Optional[bool]] = mapped_column(Boolean)
    mail_username: Mapped[Optional[str]] = mapped_column(String(256))
    mail_password: Mapped[Optional[str]] = mapped_column(String(256))

    __table_args__ = (
        Index("idx_config_user", "user_id"),
        Index("idx_config_updated", "updated_at"),
    )
