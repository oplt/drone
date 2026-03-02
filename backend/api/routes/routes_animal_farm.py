from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any

from backend.db.session import get_db
from backend.schemas.animal_farm import (
                                        HerdCreate, HerdOut,
                                        AnimalCreate, AnimalOut,
                                        AnimalPositionIn, AnimalPositionOut,
                                        HerdTaskCreate, HerdTaskOut,
                                        MissionPlanOut,
                                    )
from backend.db.repository.animal_farm_repo import LivestockRepository
from backend.services.animal_farm.risk_engine import RiskEngine

router = APIRouter(prefix="/livestock", tags=["livestock"])

repo = LivestockRepository()
risk = RiskEngine()


# -------------------------
# Herds
# -------------------------
@router.post("/herds", response_model=HerdOut)
async def create_herd(payload: HerdCreate, db: AsyncSession = Depends(get_db)):
    herd = await repo.create_herd(
        db,
        name=payload.name,
        pasture_geofence_id=payload.pasture_geofence_id,
        metadata=payload.metadata,
    )
    return herd


@router.get("/herds", response_model=List[HerdOut])
async def list_herds(limit: int = Query(100, ge=1, le=500), db: AsyncSession = Depends(get_db)):
    return await repo.list_herds(db, limit=limit)


# -------------------------
# Animals
# -------------------------
@router.post("/animals", response_model=AnimalOut)
async def create_animal(payload: AnimalCreate, db: AsyncSession = Depends(get_db)):
    existing = await repo.get_animal_by_collar(db, collar_id=payload.collar_id)
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


@router.get("/animals", response_model=List[AnimalOut])
async def list_animals(
        herd_id: Optional[int] = Query(None),
        limit: int = Query(200, ge=1, le=500),
        db: AsyncSession = Depends(get_db),
):
    return await repo.list_animals(db, herd_id=herd_id, limit=limit)


# -------------------------
# Collar ingestion
# -------------------------
@router.post("/positions", response_model=AnimalPositionOut)
async def ingest_position(payload: AnimalPositionIn, db: AsyncSession = Depends(get_db)):
    animal = await repo.get_animal_by_collar(db, collar_id=payload.collar_id)
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
async def latest_positions(herd_id: int, db: AsyncSession = Depends(get_db)):
    rows = await repo.latest_positions_for_herd(db, herd_id=herd_id)
    return {"herd_id": herd_id, "positions": rows}


# -------------------------
# Risk / Alerts (MVP)
# -------------------------
@router.get("/herds/{herd_id}/risk")
async def herd_risk_snapshot(
        herd_id: int,
        isolation_threshold_m: float = Query(250.0, ge=10.0, le=5000.0),
        db: AsyncSession = Depends(get_db),
):
    # Fetch herd to get pasture geofence id
    herds = await repo.list_herds(db, limit=500)
    herd = next((h for h in herds if h.id == herd_id), None)
    if not herd:
        raise HTTPException(status_code=404, detail="Herd not found")

    boundary = await risk.boundary_exit_alerts(db, herd_id=herd_id, pasture_geofence_id=herd.pasture_geofence_id)
    isolation = await risk.isolation_alerts(db, herd_id=herd_id, threshold_m=isolation_threshold_m)

    return {"herd_id": herd_id, "alerts": boundary + isolation}


# -------------------------
# Tasks (what your Herd Ops page will execute)
# -------------------------
@router.post("/tasks", response_model=HerdTaskOut)
async def create_task(payload: HerdTaskCreate, db: AsyncSession = Depends(get_db)):
    task = await repo.create_task(db, herd_id=payload.herd_id, type=payload.type, params=payload.params)
    return task


@router.get("/herds/{herd_id}/tasks", response_model=List[HerdTaskOut])
async def list_tasks(
        herd_id: int,
        limit: int = Query(100, ge=1, le=500),
        db: AsyncSession = Depends(get_db),
):
    return await repo.list_tasks(db, herd_id=herd_id, limit=limit)


# -------------------------
# Mission plan generation (bridge to your existing mission runner)
# -------------------------
@router.post("/tasks/{task_id}/plan", response_model=MissionPlanOut)
async def build_mission_plan(task_id: int, db: AsyncSession = Depends(get_db)):
    """
    Returns a mission dict that your existing mission endpoint can run.
    For MVP, we output a 'route' mission with waypoints.

    - herd_sweep: builds a simple loop visiting latest herd cluster centroid (naive)
    - search_locate: orbit/loiter is better, but MVP returns a 2-3 waypoint route around last point.
    """
    # Load task
    res = await db.execute(
        select(__import__("backend.db.models", fromlist=["HerdTask"]).HerdTask).where(
            __import__("backend.db.models", fromlist=["HerdTask"]).HerdTask.id == task_id
        )
    )
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get latest positions
    latest = await repo.latest_positions_for_herd(db, herd_id=task.herd_id)
    if not latest:
        raise HTTPException(status_code=400, detail="No positions for herd; ingest collar positions first.")

    # Naive centroid for herd_sweep
    lat_c = sum(p["lat"] for p in latest) / len(latest)
    lon_c = sum(p["lon"] for p in latest) / len(latest)

    if task.type == "census":
        # Census is more “CV count”; mission is a short route to centroid for now.
        mission = {
            "type": "route",
            "waypoints": [
                {"lat": lat_c, "lon": lon_c, "alt": task.params.get("altitude_msl", 30.0)},
            ],
            "speed": task.params.get("speed", 8.0),
            "altitude_agl": task.params.get("altitude_agl", 30.0),
        }
        return {"mission": mission}

    if task.type == "herd_sweep":
        # Simple 4-point “box” around centroid (placeholder until you implement true coverage path)
        d = float(task.params.get("box_deg", 0.0008))  # ~90m in lat; placeholder
        alt = float(task.params.get("altitude_msl", 35.0))
        mission = {
            "type": "route",
            "waypoints": [
                {"lat": lat_c + d, "lon": lon_c - d, "alt": alt},
                {"lat": lat_c + d, "lon": lon_c + d, "alt": alt},
                {"lat": lat_c - d, "lon": lon_c + d, "alt": alt},
                {"lat": lat_c - d, "lon": lon_c - d, "alt": alt},
            ],
            "speed": task.params.get("speed", 8.0),
            "altitude_agl": task.params.get("altitude_agl", 35.0),
        }
        return {"mission": mission}

    if task.type == "search_locate":
        # Choose an animal from params or take the most recent position
        collar_id = task.params.get("collar_id")
        target = None
        if collar_id:
            target = next((p for p in latest if p["collar_id"] == collar_id), None)
        if not target:
            target = latest[0]

        alt = float(task.params.get("altitude_msl", 30.0))
        d = float(task.params.get("offset_deg", 0.0004))
        mission = {
            "type": "route",
            "waypoints": [
                {"lat": target["lat"], "lon": target["lon"], "alt": alt},
                {"lat": target["lat"] + d, "lon": target["lon"], "alt": alt},
                {"lat": target["lat"], "lon": target["lon"] + d, "alt": alt},
            ],
            "speed": task.params.get("speed", 7.0),
            "altitude_agl": task.params.get("altitude_agl", 30.0),
        }
        return {"mission": mission}

    raise HTTPException(status_code=400, detail=f"Unsupported task type: {task.type}")