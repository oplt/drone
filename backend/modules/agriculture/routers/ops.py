from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.modules.agriculture.storage_operations import local_restore_drill, storage_readiness
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write

from backend.modules.agriculture.routers.common import (
    AGRICULTURE_SCHEMA_VERSION,
)

router = APIRouter()


@router.get("/operations/storage/readiness")
async def get_storage_readiness(org_user: OrgUser = Depends(require_org_user)) -> dict[str, Any]:
    return {"schema_version": AGRICULTURE_SCHEMA_VERSION, **storage_readiness()}


@router.post("/operations/storage/restore-drill")
async def run_storage_restore_drill(org_user: OrgUser = Depends(require_org_write)) -> dict[str, Any]:
    return {"schema_version": AGRICULTURE_SCHEMA_VERSION, **local_restore_drill()}

