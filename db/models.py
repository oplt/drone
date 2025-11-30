from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, JSON, func, UniqueConstraint, BigInteger, Index


class Base(DeclarativeBase):
    pass

class Flight(Base):
    __tablename__ = "flights"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="in_progress", nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(255))

    start_lat: Mapped[float] = mapped_column(Float, nullable=False)
    start_lon: Mapped[float] = mapped_column(Float, nullable=False)
    start_alt: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lat:  Mapped[float] = mapped_column(Float, nullable=False)
    dest_lon:  Mapped[float] = mapped_column(Float, nullable=False)
    dest_alt:  Mapped[float] = mapped_column(Float, nullable=False)

    telemetry: Mapped[list["TelemetryRecord"]] = relationship(
        back_populates="flight", cascade="all, delete-orphan"
    )
    events: Mapped[list["FlightEvent"]] = relationship(
        back_populates="flight", cascade="all, delete-orphan"
    )
    video_recordings: Mapped[list["VideoRecording"]] = relationship(
        back_populates="flight",
        cascade="all, delete-orphan",
    )

class FlightEvent(Base):
    __tablename__ = "flight_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flight_id: Mapped[int] = mapped_column(ForeignKey("flights.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    flight: Mapped["Flight"] = relationship(back_populates="events")

class TelemetryRecord(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flight_id: Mapped[Optional[int]] = mapped_column(ForeignKey("flights.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

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
    system_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


    flight: Mapped[Optional["Flight"]] = relationship(back_populates="telemetry")
    frame_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)

    __table_args__ = (
        UniqueConstraint("flight_id", "frame_id", name="uq_telemetry_flight_frame_id"),
        Index("idx_telemetry_flight_created", "flight_id", "created_at"),
        Index("idx_telemetry_created", "created_at"),
    )

class MavlinkEvent(Base):
    __tablename__ = "mavlink_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    flight_id: Mapped[int] = mapped_column(
        ForeignKey("flights.id", ondelete="CASCADE"), index=True, nullable=False
    )
    msg_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # sysid: Mapped[Optional[int]] = mapped_column(Integer)
    # compid: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON)
    time_boot_ms: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time_unix_usec: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_evt_flt_time", "flight_id", "created_at"),
        UniqueConstraint("flight_id", "msg_type", "time_boot_ms",
                         name="uq_evt_flt_type_frame"),
    )


class VideoRecording(Base):
    __tablename__ = "video_recordings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flight_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("flights.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    codec: Mapped[Optional[str]] = mapped_column(String(32))
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    fps: Mapped[Optional[float]] = mapped_column(Float)
    frame_count: Mapped[Optional[int]] = mapped_column(Integer)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    note: Mapped[Optional[str]] = mapped_column(String(255))

    flight: Mapped[Optional["Flight"]] = relationship(back_populates="video_recordings")
    frames: Mapped[list["VideoFrame"]] = relationship(
        back_populates="recording",
        cascade="all, delete-orphan",
    )


class VideoFrame(Base):
    __tablename__ = "video_frames"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    recording_id: Mapped[int] = mapped_column(
        ForeignKey("video_recordings.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)

    telemetry_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("telemetry.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    detection_summary: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(512))

    recording: Mapped["VideoRecording"] = relationship(back_populates="frames")
    telemetry: Mapped[Optional["TelemetryRecord"]] = relationship()

    __table_args__ = (
        Index("idx_video_frame_rec_ts", "recording_id", "ts"),
    )

