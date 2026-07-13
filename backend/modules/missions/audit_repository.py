from __future__ import annotations

from sqlalchemy import select

from backend.core.database.session import Session
from backend.modules.missions.flight_models import FlightEvent


class MissionAuditRepository:
    async def list_events(
        self, *, flight_id: int, limit: int, offset: int = 0
    ) -> list[FlightEvent]:
        async with Session() as db:
            rows = await db.execute(
                select(FlightEvent)
                .where(FlightEvent.flight_id == flight_id)
                .order_by(FlightEvent.created_at.asc(), FlightEvent.id.asc())
                .offset(max(0, offset))
                .limit(min(max(1, limit), 201))
            )
            return list(rows.scalars().all())


mission_audit_repository = MissionAuditRepository()
