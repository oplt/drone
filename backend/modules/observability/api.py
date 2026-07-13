from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.observability.schemas import (
    ObservabilityContextOptions,
    ObservabilityLinks,
    ObservabilityStatus,
)
from backend.modules.observability.service import (
    get_observability_context_options,
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


@router.get("/context-options", response_model=ObservabilityContextOptions)
async def context_options(
    org_user: OrgUser = Depends(require_org_user),
    db: Any = Depends(get_db),
) -> ObservabilityContextOptions:
    return await get_observability_context_options(
        db,
        org_id=org_user.org_id,
        user_id=int(org_user.user.id),
    )
