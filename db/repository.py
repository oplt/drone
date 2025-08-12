from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .session import Session
from .models import TelemetryRecord, Flight, FlightEvent
from drone.models import Telemetry as TelemetryDTO  # your dataclass

class TelemetryRepository:
    def __init__(self, session_factory: type[Session] = Session):
        self._session_factory = session_factory

    # Backwards-compatible: save a loose telemetry row (no flight)
    async def save(self, t: TelemetryDTO) -> None:
        async with self._session_factory() as s:  # type: AsyncSession
            rec = TelemetryRecord(
                lat=t.lat, lon=t.lon, alt=t.alt,
                heading=t.heading, groundspeed=t.groundspeed,
                armed=t.armed, mode=t.mode,
                battery_voltage=t.battery_voltage,
                battery_current=t.battery_current,
                battery_level=t.battery_level,
            )
            s.add(rec)
            await s.commit()

    # ---- New flight-aware methods ----

    async def create_flight(
            self,
            *,
            started_at: Optional[datetime] = None,
            start_lat: float, start_lon: float, start_alt: float,
            dest_lat: float,  dest_lon: float,  dest_alt: float,
            status: str = "in_progress",
            note: str = "",
    ) -> int:
        started_at = started_at or datetime.now(timezone.utc)
        async with self._session_factory() as s:
            f = Flight(
                started_at=started_at,
                status=status,
                note=note,
                start_lat=start_lat, start_lon=start_lon, start_alt=start_alt,
                dest_lat=dest_lat, dest_lon=dest_lon, dest_alt=dest_alt,
            )
            s.add(f)
            await s.flush()       # populates f.id
            fid = f.id
            await s.commit()
            return fid

    async def add_event(self, flight_id: int, etype: str, data: Dict[str, Any] | None = None) -> None:
        async with self._session_factory() as s:
            e = FlightEvent(flight_id=flight_id, type=etype, data=data or {})
            s.add(e)
            await s.commit()

    async def add_telemetry(self, flight_id: int, **fields) -> None:
        async with self._session_factory() as s:
            rec = TelemetryRecord(flight_id=flight_id, **fields)
            s.add(rec)
            await s.commit()

    async def finish_flight(self, flight_id: int, *, status: str, note: str = "") -> None:
        async with self._session_factory() as s:
            q = await s.execute(select(Flight).where(Flight.id == flight_id))
            f = q.scalar_one()
            f.status = status
            f.note = note
            f.ended_at = datetime.now(timezone.utc)
            await s.commit()
