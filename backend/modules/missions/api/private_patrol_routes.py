from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.modules.missions.api.mission_route_schemas import (
    PrivatePatrolPreviewIn,
    PrivatePatrolPreviewOut,
    PrivatePatrolTaskCatalogOut,
    PrivatePatrolTaskTemplateOut,
)
from backend.modules.patrol.planning import private_patrol_task_catalog
from backend.modules.missions.service.private_patrol_preview import build_private_patrol_preview

router = APIRouter(tags=["tasks"])


@router.get(
    "/missions/private-patrol/tasks",
    response_model=PrivatePatrolTaskCatalogOut,
)
async def get_private_patrol_tasks() -> PrivatePatrolTaskCatalogOut:
    return PrivatePatrolTaskCatalogOut(
        mission_category="private_patrol",
        tasks=[
            PrivatePatrolTaskTemplateOut.model_validate(item)
            for item in private_patrol_task_catalog()
        ],
    )


@router.post("/missions/private-patrol/preview", response_model=PrivatePatrolPreviewOut)
async def preview_private_patrol(
    payload: PrivatePatrolPreviewIn,
) -> PrivatePatrolPreviewOut:
    try:
        return build_private_patrol_preview(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Patrol planning inputs are invalid.") from exc
