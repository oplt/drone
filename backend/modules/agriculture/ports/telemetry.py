from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agriculture.contracts import MissionTelemetrySample
from backend.modules.agriculture.repository import agriculture_repository


async def list_mission_telemetry_for_georef(
    db: AsyncSession, *, mission_id: str
) -> list[MissionTelemetrySample]:
    """Return ordered telemetry DTOs without exposing Agriculture persistence."""
    rows = await agriculture_repository.list_telemetry(db, flight_id=mission_id)
    return [
        MissionTelemetrySample(
            timestamp_utc=row.timestamp_utc,
            lat=float(row.lat),
            lon=float(row.lon),
            relative_altitude_m=row.relative_altitude_m,
            absolute_altitude_m=row.absolute_altitude_m,
            roll_deg=row.roll_deg,
            pitch_deg=row.pitch_deg,
            yaw_deg=row.yaw_deg,
            gps_quality=row.gps_quality,
            id=getattr(row, "id", None),
        )
        for row in rows
    ]
