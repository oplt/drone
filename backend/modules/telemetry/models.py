from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database.base import Base

if TYPE_CHECKING:
    from backend.modules.missions.flight_models import Flight


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
        Index("idx_telemetry_created_at", "created_at"),
    )


class MavlinkEvent(Base):
    __tablename__ = "mavlink_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    flight_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    msg_type: Mapped[str] = mapped_column(String(64), nullable=False)
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
