from __future__ import annotations

import asyncio
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend.db.session import Session

from backend.drone.models import Coordinate
from backend.main import _build_orchestrator  # re-use your existing builder

router = APIRouter(prefix="/tasks", tags=["tasks"])

# --------------------
# Schemas
# --------------------
class WaypointIn(BaseModel):
    lat: float
    lon: float
    alt: Optional[float] = None

class MissionCreateIn(BaseModel):
    name: str = Field(default="mission", min_length=1)
    cruise_alt: float = 30.0
    waypoints: List[WaypointIn]

class MissionCreateOut(BaseModel):
    status: str
    mission_name: str
    waypoints_count: int

# --------------------
# Orchestrator singleton
# --------------------
_orch_lock = asyncio.Lock()
_orch = None

async def get_orchestrator():
    global _orch
    if _orch is not None:
        return _orch
    async with _orch_lock:
        if _orch is None:
            _orch = await _build_orchestrator()
        return _orch

# --------------------
# Endpoint
# --------------------
@router.post("/missions", response_model=MissionCreateOut)
async def create_mission(payload: MissionCreateIn):
    if len(payload.waypoints) < 2:
        raise HTTPException(status_code=400, detail="Select at least 2 coordinates.")

    orch = await get_orchestrator()

    coords: list[Coordinate] = []
    for w in payload.waypoints:
        coords.append(Coordinate(
            lat=w.lat,
            lon=w.lon,
            alt=payload.cruise_alt if w.alt is None else w.alt
        ))

    # Start immediately (non-blocking)
    asyncio.create_task(orch.run_waypoints(coords, alt=payload.cruise_alt))

    return MissionCreateOut(
        status="started",
        mission_name=payload.name,
        waypoints_count=len(coords),
    )

@router.get("/drone_home_location")
async def get_drone_home():
    orch = await get_orchestrator()
    drone = orch.drone
    hl = getattr(drone, "home_location", None)

    if not hl:
        raise HTTPException(status_code=404, detail="Drone not connected")

    return {
        "connected": True,
        "lat": float(hl.lat),
        "lon": float(hl.lon),
        "alt": float(getattr(hl, "alt", 0.0)),
    }