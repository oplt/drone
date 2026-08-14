"""Warehouse coordinate-frame routes — diagnostics and ROS sync."""

from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write

from .deps import build_coordinate_diagnostics, get_map_or_404, sync_locked_coordinate_frame_to_ros
from .router import router
from .schemas import CoordinateDiagnosticsOut


@router.get("/maps/{warehouse_map_id}/coordinate-diagnostics", response_model=CoordinateDiagnosticsOut)
async def get_coordinate_diagnostics(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> CoordinateDiagnosticsOut:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    payload = await build_coordinate_diagnostics(db, warehouse_map_id=warehouse_map_id)
    return CoordinateDiagnosticsOut.model_validate(payload)


@router.post("/maps/{warehouse_map_id}/coordinate-frames/sync-ros")
async def sync_coordinate_frame_to_ros(
    warehouse_map_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> dict[str, object]:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    synced, detail = await sync_locked_coordinate_frame_to_ros(db, warehouse_map_id=warehouse_map_id)
    if not synced:
        raise HTTPException(409, detail)
    return {"synced": True, "detail": detail}
