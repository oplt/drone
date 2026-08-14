from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.database.session import get_db
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import require_user
from backend.modules.property_patrol import repository as property_patrol_repository
from backend.modules.property_patrol.api.route_support import (
    get_site,
    mission_command,
    resolve_template_for_preview,
)
from backend.modules.property_patrol.schemas import (
    MissionRunOut,
    MissionStartIn,
    MissionValidateIn,
    RoutePreviewIn,
    RoutePreviewOut,
)
from backend.modules.property_patrol.services.dispatch import dispatch_service
from backend.modules.property_patrol.services.policy import policy_engine
from backend.modules.property_patrol.services.route_planner import route_planner

logger = logging.getLogger(__name__)
router = APIRouter(tags=["property-patrol"])
AsyncSession = Any


@router.post("/route-preview", response_model=RoutePreviewOut)
async def route_preview(
    payload: RoutePreviewIn, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    site = await get_site(db, payload.site_id, user)
    template = await resolve_template_for_preview(db, site, payload)
    waypoints, stats = route_planner.generate(site=site, template=template)
    validation = policy_engine.validate_route(site=site, template=template, waypoints=waypoints)
    logger.info(
        "property_patrol_route_generated",
        extra={"site_id": site.id, "waypoints": len(waypoints), "ok": validation.ok},
    )
    return RoutePreviewOut(waypoints=waypoints, stats=stats, validation=validation)


@router.post("/missions/validate", response_model=RoutePreviewOut)
async def validate_mission(
    payload: MissionValidateIn, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    site = await get_site(db, payload.site_id, user)
    template = await resolve_template_for_preview(db, site, payload)
    waypoints = (
        [wp.model_dump() for wp in payload.route_waypoints]
        if payload.route_waypoints
        else route_planner.generate(site=site, template=template)[0]
    )
    validation = policy_engine.validate_route(site=site, template=template, waypoints=waypoints)
    return RoutePreviewOut(
        waypoints=waypoints, stats={"waypoints": len(waypoints)}, validation=validation
    )


@router.post("/missions/start", response_model=MissionRunOut)
async def start_mission(
    payload: MissionStartIn, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    site = await get_site(db, payload.site_id, user)
    template = await resolve_template_for_preview(db, site, payload)
    waypoints, _stats = route_planner.generate(site=site, template=template)
    run, validation = await dispatch_service.create_validated_run(
        db=db,
        site=site,
        template=template,
        route_waypoints=waypoints,
        mission_type=payload.mission_type,
        operator_id=getattr(user, "id", None),
        drone_id=payload.drone_id,
    )
    if not validation.ok:
        await db.commit()
        raise HTTPException(status_code=422, detail=[err.model_dump() for err in validation.errors])
    await dispatch_service.dispatch_after_preflight(db=db, run=run)
    await db.commit()
    await db.refresh(run)
    return run


@router.get("/missions", response_model=Page[MissionRunOut])
async def list_missions(
    site_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    page_limit = clamp_page_limit(limit)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    rows = await property_patrol_repository.list_runs(
        db, site_id=site_id, limit=page_limit + 1, offset=page_offset
    )
    return page_from_offset(
        [MissionRunOut.model_validate(row) for row in rows],
        limit=page_limit,
        offset=page_offset,
    )


@router.get("/missions/{mission_run_id}", response_model=MissionRunOut)
async def get_mission(
    mission_run_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    return await property_patrol_repository.get_run(db, mission_run_id)


@router.post("/missions/{mission_run_id}/approve", response_model=MissionRunOut)
async def approve_mission(
    mission_run_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    run = await property_patrol_repository.get_run(db, mission_run_id)
    preflight = await dispatch_service.dispatch_after_preflight(db=db, run=run)
    if not preflight.ok:
        await db.commit()
        raise HTTPException(status_code=422, detail=[err.model_dump() for err in preflight.errors])
    await db.commit()
    await db.refresh(run)
    return run


@router.post("/missions/{mission_run_id}/pause", response_model=MissionRunOut)
async def pause_mission(
    mission_run_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    return await mission_command(mission_run_id, "pause", db)


@router.post("/missions/{mission_run_id}/resume", response_model=MissionRunOut)
async def resume_mission(
    mission_run_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    return await mission_command(mission_run_id, "resume", db)


@router.post("/missions/{mission_run_id}/abort", response_model=MissionRunOut)
async def abort_mission(
    mission_run_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    return await mission_command(mission_run_id, "abort", db)


@router.post("/missions/{mission_run_id}/return-home", response_model=MissionRunOut)
async def return_home_mission(
    mission_run_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)
):
    return await mission_command(mission_run_id, "return-home", db)
