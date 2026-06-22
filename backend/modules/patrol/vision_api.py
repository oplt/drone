from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.infrastructure.camera.runtime import (
    drone_video_link_connected,
    shared_video_runtime,
)
from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.modules.identity.dependencies import require_user
from backend.modules.patrol.vision.runtime import ml_runtime
from backend.modules.patrol.vision.stream_reader import resolve_ml_stream_source

router = APIRouter(prefix="/api/ml", tags=["ml"])


class MLStartIn(BaseModel):
    stream_source: str | int | None = Field(default=None)


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
    stream_source = resolve_ml_stream_source(body.stream_source)
    if body.stream_source is None:
        if not drone_video_link_connected():
            return {
                "running": False,
                "message": "Drone is not connected.",
            }
        try:
            await shared_video_runtime.ensure_running()
        except RuntimeError as exc:
            return {
                "running": False,
                "message": str(exc),
            }
    return await ml_runtime.start(stream_source=stream_source)


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
