from __future__ import annotations

from sqlalchemy import select

from backend.core.database.session import Session
from backend.modules.missions.flight_models import FlightEvent


class MissionAuditRepository:
    async def list_events(self, *, flight_id: int, limit: int) -> list[FlightEvent]:
        async with Session() as db:
            rows = await db.execute(
                select(FlightEvent)
                .where(FlightEvent.flight_id == flight_id)
                .order_by(FlightEvent.created_at.asc())
                .limit(min(limit, 200))
            )
            return list(rows.scalars().all())


mission_audit_repository = MissionAuditRepository()
