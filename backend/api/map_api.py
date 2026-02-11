from pydantic import BaseModel, Field
from typing import List, Optional
from fastapi import APIRouter

router = APIRouter(prefix="/tasks", tags=["tasks"])


class WaypointIn(BaseModel):
    lat: float
    lon: float
    alt: Optional[float] = None


class MissionCreateIn(BaseModel):
    name: str = Field(..., min_length=1)
    cruise_alt: float = 30.0
    waypoints: List[WaypointIn]


@router.post("/missions")
async def create_mission(payload: MissionCreateIn):
    # Store in DB if you want, or immediately dispatch to orchestrator
    # For now, just return an ID and echo
    return {"id": payload.name, "count": len(payload.waypoints)}
