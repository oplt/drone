from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import (
    OrgUser,
    require_mission_exec,
    require_org_user,
    require_org_write,
)
from backend.modules.livestock.mission_planner import build_mission
from backend.modules.livestock.repository import LivestockRepository
from backend.modules.livestock.risk_service import RiskEngine
from backend.modules.livestock.schemas import (
    AnimalCreate,
    AnimalOut,
    AnimalPositionIn,
    AnimalPositionOut,
    HerdCreate,
    HerdOut,
    HerdTaskCreate,
    HerdTaskOut,
    MissionPlanOut,
)

router = APIRouter(prefix="/livestock", tags=["livestock"])

repo = LivestockRepository()
risk = RiskEngine()


def _org_id(org_user: OrgUser) -> int:
    if org_user.org_id is None:
        raise HTTPException(status_code=403, detail="Organization membership required")
    return org_user.org_id


# -------------------------
# Herds
# -------------------------
@router.post("/herds", response_model=HerdOut)
async def create_herd(
    payload: HerdCreate,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
):
    herd = await repo.create_herd(
        db,
        org_id=_org_id(org_user),
        name=payload.name,
        pasture_geofence_id=payload.pasture_geofence_id,
        metadata=payload.metadata,
    )
    return herd


@router.get("/herds", response_model=list[HerdOut])
async def list_herds(
    limit: int = Query(100, ge=1, le=500),
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    return await repo.list_herds(db, org_id=_org_id(org_user), limit=limit)


# -------------------------
# Animals
# -------------------------
@router.post("/animals", response_model=AnimalOut)
async def create_animal(
    payload: AnimalCreate,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
):
    org_id = _org_id(org_user)
    if await repo.get_herd(db, org_id=org_id, herd_id=payload.herd_id) is None:
        raise HTTPException(status_code=404, detail="Herd not found")
    existing = await repo.get_animal_by_collar(db, org_id=org_id, collar_id=payload.collar_id)
    if existing:
        raise HTTPException(status_code=409, detail="collar_id already exists")
    return await repo.create_animal(
        db,
        herd_id=payload.herd_id,
        collar_id=payload.collar_id,
        name=payload.name,
        species=payload.species,
        metadata=payload.metadata,
    )


@router.get("/animals", response_model=list[AnimalOut])
async def list_animals(
    herd_id: int | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    return await repo.list_animals(db, org_id=_org_id(org_user), herd_id=herd_id, limit=limit)


# -------------------------
# Collar ingestion
# -------------------------
@router.post("/positions", response_model=AnimalPositionOut)
async def ingest_position(
    payload: AnimalPositionIn,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
):
    animal = await repo.get_animal_by_collar(
        db, org_id=_org_id(org_user), collar_id=payload.collar_id
    )
    if not animal:
        raise HTTPException(status_code=404, detail="Unknown collar_id. Create animal first.")
    pos = await repo.add_position(
        db,
        animal_id=animal.id,
        lat=payload.lat,
        lon=payload.lon,
        alt=payload.alt,
        speed_mps=payload.speed_mps,
        activity=payload.activity,
        source=payload.source,
        raw=payload.raw,
    )
    return pos


@router.get("/herds/{herd_id}/latest_positions")
async def latest_positions(
    herd_id: int,
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await repo.latest_positions_for_herd(db, org_id=_org_id(org_user), herd_id=herd_id)
    return {"herd_id": herd_id, "positions": rows}


@router.get("/herds/{herd_id}/risk")
async def herd_risk_snapshot(
    herd_id: int,
    isolation_threshold_m: float = Query(250.0, ge=10.0, le=5000.0),
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    herd = await repo.get_herd(db, org_id=_org_id(org_user), herd_id=herd_id)
    if not herd:
        raise HTTPException(status_code=404, detail="Herd not found")

    boundary = await risk.boundary_exit_alerts(
        db, herd_id=herd_id, pasture_geofence_id=herd.pasture_geofence_id
    )
    isolation = await risk.isolation_alerts(db, herd_id=herd_id, threshold_m=isolation_threshold_m)

    return {"herd_id": herd_id, "alerts": boundary + isolation}


# -------------------------
# Tasks (what your Herd Ops page will execute)
# -------------------------
@router.post("/tasks", response_model=HerdTaskOut)
async def create_task(
    payload: HerdTaskCreate,
    org_user: OrgUser = Depends(require_mission_exec),
    db: AsyncSession = Depends(get_db),
):
    if await repo.get_herd(db, org_id=_org_id(org_user), herd_id=payload.herd_id) is None:
        raise HTTPException(status_code=404, detail="Herd not found")
    task = await repo.create_task(
        db, herd_id=payload.herd_id, type=payload.type, params=payload.params
    )
    return task


@router.get("/herds/{herd_id}/tasks", response_model=list[HerdTaskOut])
async def list_tasks(
    herd_id: int,
    limit: int = Query(100, ge=1, le=500),
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    return await repo.list_tasks(db, org_id=_org_id(org_user), herd_id=herd_id, limit=limit)


# -------------------------
# Mission plan generation (bridge to your existing mission runner)
# -------------------------
@router.post("/tasks/{task_id}/plan", response_model=MissionPlanOut)
async def build_mission_plan(
    task_id: int,
    org_user: OrgUser = Depends(require_mission_exec),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns a mission dict that your existing mission endpoint can run.
    For MVP, we output a 'route' mission with waypoints.

    - herd_sweep: builds a simple loop visiting latest herd cluster centroid (naive)
    - search_locate: orbit/loiter is better, but MVP returns a 2-3 waypoint route around last point.
    """
    org_id = _org_id(org_user)
    task = await repo.get_task(db, org_id=org_id, task_id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    latest = await repo.latest_positions_for_herd(db, org_id=org_id, herd_id=task.herd_id)
    if not latest:
        raise HTTPException(
            status_code=400,
            detail="No positions for herd; ingest collar positions first.",
        )

    try:
        mission_plan = build_mission(task, latest)
        try:
            from backend.modules.agents.hooks import schedule_livestock_plan_narrative

            schedule_livestock_plan_narrative(task_id=task_id, mission_plan=mission_plan)
        except Exception:
            pass
        return MissionPlanOut(mission=mission_plan)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
