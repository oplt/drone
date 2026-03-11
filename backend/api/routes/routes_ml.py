from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth.deps import require_user
from backend.messaging.websocket import telemetry_manager
from backend.ml.patrol.config import ml_settings
from backend.ml.patrol.runtime import ml_runtime

router = APIRouter(prefix="/api/ml", tags=["ml"])


class MLStartIn(BaseModel):
    stream_source: Optional[str | int] = Field(default=None)


class ZonePointIn(BaseModel):
    lat: float
    lon: float


class ZoneIn(BaseModel):
    name: str
    polygon: list[ZonePointIn] = Field(..., min_length=3)
    restricted: bool = True


class MLZonesIn(BaseModel):
    zones: list[ZoneIn] = Field(default_factory=list)


class MLSimulatedEventOut(BaseModel):
    ok: bool = True
    detail: str


@router.get("/status")
async def get_ml_status(user=Depends(require_user)) -> dict[str, Any]:
    return ml_runtime.status()


@router.post("/start")
async def start_ml(body: MLStartIn, user=Depends(require_user)) -> dict[str, Any]:
    if not ml_settings.enabled:
        raise HTTPException(
            status_code=412,
            detail="ML pipeline disabled. Set ML_ENABLED=1 before starting the anomaly pipeline.",
        )
    return await ml_runtime.start(stream_source=body.stream_source)


@router.post("/stop")
async def stop_ml(user=Depends(require_user)) -> dict[str, Any]:
    return await ml_runtime.stop()


@router.post("/zones")
async def configure_zones(body: MLZonesIn, user=Depends(require_user)) -> dict[str, Any]:
    zones = [
        {
            "name": item.name,
            "polygon": [{"lat": p.lat, "lon": p.lon} for p in item.polygon],
            "restricted": item.restricted,
        }
        for item in body.zones
    ]
    return ml_runtime.set_zones(zones)


@router.post("/simulate")
async def simulate_ml_event(user=Depends(require_user)) -> MLSimulatedEventOut:
    await telemetry_manager.broadcast(
        {"type": "ml_status", "message": "Simulated ML event channel test"}
    )
    return MLSimulatedEventOut(detail="Broadcasted simulated ML status event over websocket")
