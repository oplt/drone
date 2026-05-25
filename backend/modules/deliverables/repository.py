from __future__ import annotations

from sqlalchemy import select

from backend.core.database.session import Session
from backend.modules.deliverables.models import ExportJob


class ExportJobRepository:
    async def create(
        self,
        *,
        org_id: int | None,
        project_id: int | None,
        flight_id: str,
        requested_by: int,
    ) -> ExportJob:
        job = ExportJob(
            org_id=org_id,
            project_id=project_id,
            flight_id=flight_id,
            requested_by=requested_by,
            status="pending",
        )
        async with Session() as db:
            db.add(job)
            await db.flush()
            await db.commit()
            await db.refresh(job)
        return job

    async def get_for_flight(self, *, job_id: int, flight_id: str) -> ExportJob | None:
        async with Session() as db:
            return await db.scalar(
                select(ExportJob).where(ExportJob.id == job_id, ExportJob.flight_id == flight_id)
            )
