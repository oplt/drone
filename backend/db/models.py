from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any
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
)


class Base(DeclarativeBase):
    pass


class Flight(Base):
    __tablename__ = "flights"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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

    telemetry: Mapped[list["TelemetryRecord"]] = relationship(
        back_populates="flight", cascade="all, delete-orphan"
    )
    events: Mapped[list["FlightEvent"]] = relationship(
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


class SettingsRow(Base):
    """
    Single-row settings table (id=1) storing all config values as JSON.
    """
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
