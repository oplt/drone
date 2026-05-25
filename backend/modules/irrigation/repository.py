from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.irrigation.models import (
    AnomalyZone,
    CaptureRecord,
    InspectionPoint,
    ProcessedFieldLayer,
)


class IrrigationRepository:
    async def save_capture(self, db: AsyncSession, *, capture: CaptureRecord) -> CaptureRecord:
        await db.commit()
        await db.refresh(capture)
        return capture

    async def summary_components(
        self, db: AsyncSession, *, mission_id: str
    ) -> tuple[
        list[CaptureRecord], ProcessedFieldLayer | None, list[AnomalyZone], list[InspectionPoint]
    ]:
        captures = list(
            (
                await db.execute(
                    select(CaptureRecord)
                    .where(CaptureRecord.mission_id == mission_id)
                    .order_by(CaptureRecord.timestamp_utc.asc())
                )
            )
            .scalars()
            .all()
        )
        layer = await db.scalar(
            select(ProcessedFieldLayer).where(ProcessedFieldLayer.mission_id == mission_id)
        )
        zones = list(
            (
                await db.execute(
                    select(AnomalyZone)
                    .where(AnomalyZone.mission_id == mission_id)
                    .order_by(AnomalyZone.severity.desc(), AnomalyZone.id.asc())
                )
            )
            .scalars()
            .all()
        )
        points = list(
            (
                await db.execute(
                    select(InspectionPoint)
                    .where(InspectionPoint.mission_id == mission_id)
                    .order_by(InspectionPoint.priority.desc(), InspectionPoint.id.asc())
                )
            )
            .scalars()
            .all()
        )
        return captures, layer, zones, points
