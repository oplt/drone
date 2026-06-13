from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.observability.schemas import ObservabilityLinks, ObservabilityStatus
from backend.modules.observability.service import (
    get_observability_links,
    get_observability_status,
)

router = APIRouter(prefix="/api/observability", tags=["observability"])


@router.get("/links", response_model=ObservabilityLinks)
async def links(_org_user: OrgUser = Depends(require_org_user)) -> ObservabilityLinks:
    return get_observability_links()


@router.get("/status", response_model=ObservabilityStatus)
async def status(_org_user: OrgUser = Depends(require_org_user)) -> ObservabilityStatus:
    return await get_observability_status()
