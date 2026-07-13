from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
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
    from backend.modules.patrol.models import PatrolDetection, PatrolIncident
    from backend.modules.telemetry.models import TelemetryRecord


class FlightStatus(str, Enum):  # noqa: UP042 - database enum values must remain stable
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

    __table_args__ = (
        Index("idx_flights_started_at", "started_at"),
        Index("idx_flights_ended_at", "ended_at"),
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
