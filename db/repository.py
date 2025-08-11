from __future__ import annotations
import asyncio
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from core.models import Telemetry
from .session import Session
from .models import TelemetryRecord

class TelemetryRepository:
    def __init__(self, session_factory: type[Session] = Session):
        self._session_factory = session_factory

    async def save(self, t: Telemetry) -> None:
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
