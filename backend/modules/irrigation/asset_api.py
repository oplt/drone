"""Authorized irrigation asset routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.irrigation.asset_access import resolve_owned_asset

router = APIRouter(prefix="/irrigation-assets", tags=["irrigation-assets"])


@router.get("/{asset_path:path}")
async def get_irrigation_asset(
    asset_path: str,
    db: Any = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> FileResponse:
    path = await resolve_owned_asset(db, asset_path=asset_path, user=org_user.user)
    if path is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(
        path,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
