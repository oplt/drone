from __future__ import annotations

from backend.modules.deliverables.models import ExportJob
from backend.modules.deliverables.repository import ExportJobRepository
from backend.modules.identity.models import User
from backend.modules.missions.repository import mission_runtime_repo


class MissionExportService:
    def __init__(self, repository: ExportJobRepository | None = None) -> None:
        self.repository = repository or ExportJobRepository()

    async def create_for_user(self, *, flight_id: str, user: User) -> ExportJob | None:
        runtime = await mission_runtime_repo.get_by_client_id_for_user(flight_id, int(user.id))
        if runtime is None:
            return None
        return await self.repository.create(
            org_id=user.org_id,
            project_id=runtime.project_id,
            flight_id=flight_id,
            requested_by=int(user.id),
        )

    async def get_for_user(self, *, flight_id: str, job_id: int, user: User) -> ExportJob | None:
        job = await self.repository.get_for_flight(job_id=job_id, flight_id=flight_id)
        if job is None:
            return None
        if job.requested_by != user.id:
            return None
        if job.org_id is not None and job.org_id != user.org_id:
            return None
        return job


mission_export_service = MissionExportService()
