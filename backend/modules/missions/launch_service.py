from __future__ import annotations

from backend.core.database.session import Session
from backend.modules.organizations.service import get_default_project


class MissionLaunchService:
    async def default_project_id(self, *, org_id: int | None) -> int | None:
        if org_id is None:
            return None
        async with Session() as db:
            project = await get_default_project(db, org_id=int(org_id))
            return int(project.id) if project else None


mission_launch_service = MissionLaunchService()
