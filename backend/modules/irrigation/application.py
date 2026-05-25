from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.irrigation.models import (
    AnomalyZone,
    CaptureRecord,
    InspectionPoint,
    ProcessedFieldLayer,
)
from backend.modules.irrigation.repository import IrrigationRepository


class IrrigationApplication:
    def __init__(self, repository: IrrigationRepository | None = None) -> None:
        self.repository = repository or IrrigationRepository()

    async def save_capture(self, db: AsyncSession, *, capture: CaptureRecord) -> CaptureRecord:
        return await self.repository.save_capture(db, capture=capture)

    async def summary_components(
        self, db: AsyncSession, *, mission_id: str
    ) -> tuple[
        list[CaptureRecord], ProcessedFieldLayer | None, list[AnomalyZone], list[InspectionPoint]
    ]:
        return await self.repository.summary_components(db, mission_id=mission_id)


irrigation_application = IrrigationApplication()
