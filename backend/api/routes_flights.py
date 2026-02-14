from __future__ import annotations
import time
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from backend.db.session import get_db, Session
from backend.drone.models import Coordinate
from backend.main import _build_orchestrator
from backend.auth.deps import require_user
import asyncio
from backend.messaging.websocket import telemetry_manager


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
    flight_id: str
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
async def create_mission(
        payload: MissionCreateIn,
        db: Session = Depends(get_db),
        user = Depends(require_user),
):
    """Create and execute a mission - returns flight_id for tracking"""
    if len(payload.waypoints) < 2:
        raise HTTPException(status_code=400, detail="Select at least 2 coordinates.")

    # Convert waypoints to Coordinate objects
    coords: list[Coordinate] = []
    for w in payload.waypoints:
        coords.append(
            Coordinate(
                lat=w.lat,
                lon=w.lon,
                alt=payload.cruise_alt if w.alt is None else w.alt
            )
        )

    # Generate a client-facing flight ID
    client_flight_id = f"flight_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    # Get orchestrator
    orch = await get_orchestrator()

    # Store mission metadata
    orch.current_mission_name = payload.name
    orch.current_client_flight_id = client_flight_id

    # Start mission execution in background
    asyncio.create_task(
        execute_mission(
            orch,
            coords,
            payload.cruise_alt,
            payload.name,
        )
    )

    return MissionCreateOut(
        flight_id=client_flight_id,
        status="executing",
        mission_name=payload.name,
        waypoints_count=len(coords),
    )

async def execute_mission(
        orch,
        coords: list[Coordinate],
        cruise_alt: float,
        mission_name: str,
):
    """Execute mission in background - orchestrator handles all initialization"""
    try:
        # The orchestrator's run_waypoints handles:
        # - Drone connection
        # - Flight record creation
        # - Telemetry streaming (via telemetry_manager)
        # - Background tasks (heartbeat, MQTT, etc.)
        await orch.run_waypoints(coords, alt=cruise_alt)
        print(f"✅ Mission '{mission_name}' completed successfully")
    except Exception as e:
        print(f"❌ Mission '{mission_name}' failed: {e}")
        # Log the error but don't re-raise



@router.get("/flight/status")
async def get_flight_status():
    """Get current flight status and telemetry info"""
    try:
        orch = await get_orchestrator()

        # Get current flight_id from orchestrator if available
        flight_id = None
        if hasattr(orch, "_flight_id") and orch._flight_id:
            flight_id = str(orch._flight_id)

        # Get mission name if available
        mission_name = getattr(orch, "current_mission_name", "Unknown")

        # Get telemetry status
        from backend.messaging.websocket import telemetry_manager

        has_position = bool(
            telemetry_manager.last_telemetry.get("position", {}).get("lat", 0)
            or telemetry_manager.last_telemetry.get("position", {}).get("lon", 0)
        )

        return {
            "flight_id": flight_id,
            "mission_name": mission_name,
            "telemetry": {
                "running": telemetry_manager._running,
                "active_connections": len(telemetry_manager.active_connections),
                "has_position_data": has_position,
                "last_update": telemetry_manager.last_telemetry.get("timestamp", 0),
                "position": telemetry_manager.last_telemetry.get("position", {}),
            },
            "orchestrator": {
                "ready": orch is not None,
                "has_drone": hasattr(orch, "drone") and orch.drone is not None,
                "drone_connected": hasattr(orch, "drone")
                                   and hasattr(orch.drone, "vehicle")
                                   and orch.drone.vehicle is not None,
            },
        }
    except Exception as e:
        return {
            "error": str(e),
            "telemetry": {
                "running": telemetry_manager._running,
                "active_connections": len(telemetry_manager.active_connections),
            },
        }


@router.get("/drone/position")
async def get_drone_position():
    """Get drone's current position from telemetry"""
    from backend.messaging.websocket import telemetry_manager

    position = telemetry_manager.last_telemetry.get("position", {})
    lat = position.get("lat", 0)
    lon = position.get("lon", 0)

    # Check if position is valid (not 0,0)
    has_valid_position = lat != 0 and lon != 0

    return {
        "has_position": has_valid_position,
        "lat": lat,
        "lng": lon,
        "alt": position.get("alt", 0),
        "relative_alt": position.get("relative_alt", 0),
        "timestamp": telemetry_manager.last_telemetry.get("timestamp", 0),
    }


@router.post("/telemetry/start")
async def start_telemetry():
    """Explicitly start telemetry stream"""
    if telemetry_manager._running:
        return {
            "status": "already_running",
            "message": "Telemetry stream is already running",
        }

    try:
        telemetry_manager.start_telemetry_stream()
        return {"status": "started", "message": "Telemetry stream started successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to start telemetry: {str(e)}"
        )


@router.post("/telemetry/stop")
async def stop_telemetry():
    """Stop telemetry stream"""
    if not telemetry_manager._running:
        return {
            "status": "already_stopped",
            "message": "Telemetry stream is already stopped",
        }

    try:
        telemetry_manager.stop_telemetry_stream()
        return {"status": "stopped", "message": "Telemetry stream stopped successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to stop telemetry: {str(e)}"
        )
