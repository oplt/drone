import asyncio
import logging
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.entrypoints.cli.run_mission import _build_orchestrator
from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.modules.identity.dependencies import require_admin, require_user
from backend.modules.missions.repository import mission_runtime_repo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post("/connect")
async def connect_drone_and_telemetry(user=Depends(require_user)):
    """Build orchestrator (connects drone) and start telemetry in one call."""
    try:
        orch = await _build_orchestrator()
    except Exception as e:
        logger.error(f"Failed to connect drone: {e}")
        raise HTTPException(status_code=500, detail=f"Drone connection failed: {e!s}")

    drone = getattr(orch, "drone", None)
    if drone and not getattr(drone, "vehicle", None):
        try:
            await asyncio.to_thread(drone.connect)
            logger.info("DroneKit vehicle connected via /telemetry/connect")
        except Exception as e:
            logger.error(f"DroneKit vehicle connect failed: {e}")
            raise HTTPException(status_code=500, detail=f"Drone vehicle connection failed: {e!s}")

    if not telemetry_manager.runtime_snapshot()["running"]:
        try:
            await orch.start_live_telemetry()
        except Exception as e:
            logger.error(f"Failed to start telemetry: {e}")
            raise HTTPException(status_code=500, detail=f"Telemetry start failed: {e!s}")

    return {
        "status": "connected",
        "drone": drone is not None and getattr(drone, "vehicle", None) is not None,
        "telemetry_running": telemetry_manager.runtime_snapshot()["running"],
    }


@router.post("/start")
async def start_telemetry_stream(user=Depends(require_admin)):
    """
    Start the WebSocket telemetry stream.
    This should be called when a mission starts.
    """
    if telemetry_manager.runtime_snapshot()["running"]:
        return {
            "status": "already_running",
            "message": "Telemetry stream is already running",
        }

    try:
        orch = await _build_orchestrator()
        await orch.start_live_telemetry()
        return {
            "status": "started",
            "message": "Telemetry stream started successfully",
            "connections": telemetry_manager.client_count(),
        }
    except Exception as e:
        logger.error(f"Failed to start telemetry stream: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start telemetry: {e!s}")


@router.post("/stop")
async def stop_telemetry_stream(user=Depends(require_admin)):
    """
    Stop the WebSocket telemetry stream.
    This should be called when a mission ends.
    """
    if not telemetry_manager.runtime_snapshot()["running"]:
        return {
            "status": "already_stopped",
            "message": "Telemetry stream is already stopped",
        }

    try:
        orch = await _build_orchestrator()
        await orch.stop_live_telemetry()
        return {
            "status": "stopped",
            "message": "Telemetry stream stopped successfully",
            "connections": telemetry_manager.client_count(),
        }
    except Exception as e:
        logger.error(f"Failed to stop telemetry stream: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop telemetry: {e!s}")


@router.get("/status")
async def get_telemetry_status(user=Depends(require_user)):
    """Get current telemetry status"""
    telemetry = telemetry_manager.runtime_snapshot()
    return {
        "running": telemetry["running"],
        "source_connected": telemetry["source_connected"],
        "active_connections": telemetry["active_connections"],
        "last_telemetry_timestamp": telemetry["last_update"],
    }


@router.get("/runtime-metrics")
async def get_runtime_metrics(user=Depends(require_user)):
    """Return live orchestrator runtime metrics: queue depths, dropped counts, ingest rate."""
    orch = await _build_orchestrator()
    return orch.get_runtime_metrics()


@router.get("/shadow-report")
async def get_shadow_report(user=Depends(require_user)):
    """Compare old direct-DB-write path vs new queued path under shadow mode.

    Shadow mode is enabled by setting ORCHESTRATOR_SHADOW_MODE=true in the
    environment. When active, both paths run simultaneously so you can verify
    the new path is stable before fully removing the legacy write.
    Once error rates are equivalent, set ORCHESTRATOR_SHADOW_MODE=false and
    mark the shadow tasks done in todos.txt.
    """
    orch = await _build_orchestrator()
    return orch.get_shadow_report()


@router.get("/ops-health")
async def get_ops_health(user=Depends(require_user)):
    """Return a customer-visible operational health snapshot."""
    orch = await _build_orchestrator()
    telemetry = telemetry_manager.runtime_snapshot()
    runtime_metrics = orch.get_runtime_metrics()
    shadow_report = orch.get_shadow_report()

    def _queue_snapshot(prefix: str) -> dict[str, float | int]:
        depth = int(runtime_metrics.get(f"{prefix}_depth", 0) or 0)
        capacity = int(runtime_metrics.get(f"{prefix}_capacity", 0) or 0)
        utilization_pct = round((depth / capacity) * 100, 1) if capacity > 0 else 0.0
        return {
            "depth": depth,
            "capacity": capacity,
            "utilization_pct": utilization_pct,
        }

    now = time.time()
    last_update = float(telemetry["last_update"] or 0.0)
    telemetry_age = round(max(0.0, now - last_update), 1) if last_update > 0 else None
    recent_threshold_sec = 15.0
    has_recent_update = telemetry_age is not None and telemetry_age <= recent_threshold_sec

    video_status: dict[str, object] = {"available": False}
    if getattr(orch, "video", None) is not None:
        try:
            status = dict(orch.video.get_connection_status())
            video_status = {
                "available": True,
                "healthy": bool(status.get("healthy")),
                "frame_count": int(status.get("frame_count") or 0),
                "fps": float(status.get("fps") or 0.0),
                "resolution": str(status.get("resolution") or ""),
                "recording": bool(status.get("recording")),
                "recording_file": status.get("recording_file"),
            }
        except Exception as exc:  # pragma: no cover - defensive read path
            logger.warning("Failed to read video health snapshot: %s", exc)
            video_status = {
                "available": True,
                "healthy": False,
                "error": str(exc),
            }

    active_mission = None
    active_db_row = await mission_runtime_repo.get_active()
    if active_db_row is not None and int(active_db_row.user_id or 0) == int(user.id):
        active_mission = {
            "flight_id": active_db_row.client_flight_id,
            "mission_name": active_db_row.mission_name,
            "mission_type": active_db_row.mission_type,
            "state": active_db_row.state,
            "updated_at": (
                active_db_row.updated_at.timestamp()
                if getattr(active_db_row, "updated_at", None) is not None
                else None
            ),
        }

    alerts: list[str] = []
    if not telemetry["running"]:
        alerts.append("Telemetry runtime is not running.")
    elif not telemetry["source_connected"]:
        alerts.append("Telemetry runtime is up, but the drone data source is disconnected.")
    elif not has_recent_update:
        alerts.append("Telemetry updates are stale.")

    if runtime_metrics.get("dropped_db_events", 0):
        alerts.append("Runtime dropped DB events under queue pressure.")

    for label, snapshot in {
        "flight events": _queue_snapshot("db_event_queue"),
        "mission lifecycle": _queue_snapshot("db_lifecycle_queue"),
        "raw ingest": _queue_snapshot("raw_event_queue"),
    }.items():
        if snapshot["utilization_pct"] >= 80:
            alerts.append(f"{label.capitalize()} queue utilization is above 80%.")

    if shadow_report["shadow_mode_active"] and shadow_report["old_path"]["writes_failed"] > 0:
        alerts.append("Shadow-mode writes are failing and need investigation.")

    if video_status.get("available") and not bool(video_status.get("healthy", False)):
        alerts.append("Video stream health is degraded.")

    overall_status = "healthy"
    if alerts:
        overall_status = "offline" if not telemetry["source_connected"] else "degraded"

    return {
        "status": overall_status,
        "generated_at": now,
        "telemetry": {
            "running": telemetry["running"],
            "source_connected": telemetry["source_connected"],
            "active_connections": telemetry["active_connections"],
            "last_update": last_update,
            "last_update_age_sec": telemetry_age,
            "has_recent_update": has_recent_update,
            "recent_threshold_sec": recent_threshold_sec,
        },
        "video": video_status,
        "queues": {
            "db_event": _queue_snapshot("db_event_queue"),
            "db_lifecycle": _queue_snapshot("db_lifecycle_queue"),
            "raw_event": _queue_snapshot("raw_event_queue"),
        },
        "runtime_metrics": runtime_metrics,
        "shadow": shadow_report,
        "active_mission": active_mission,
        "alerts": alerts,
    }


ManualFlightCommand = Literal[
    "forward",
    "backward",
    "left",
    "right",
    "yaw_left",
    "yaw_right",
    "up",
    "down",
    "hold",
    "takeoff",
    "land",
]

ManualCommandPhase = Literal["start", "hold", "stop"]


class ManualControlIn(BaseModel):
    command: ManualFlightCommand
    phase: ManualCommandPhase = "start"
    source: str = Field(default="keyboard", max_length=32)
    flight_id: str | None = None


_VELOCITY_STEP_MPS = 1.0
_YAW_RATE_DPS = 30.0
_ALTITUDE_STEP_MPS = 0.8

_COMMAND_VELOCITY_MAP: dict[str, tuple[float, float, float, float]] = {
    "forward": (_VELOCITY_STEP_MPS, 0.0, 0.0, 0.0),
    "backward": (-_VELOCITY_STEP_MPS, 0.0, 0.0, 0.0),
    "left": (0.0, -_VELOCITY_STEP_MPS, 0.0, 0.0),
    "right": (0.0, _VELOCITY_STEP_MPS, 0.0, 0.0),
    "yaw_left": (0.0, 0.0, 0.0, -_YAW_RATE_DPS),
    "yaw_right": (0.0, 0.0, 0.0, _YAW_RATE_DPS),
    "up": (0.0, 0.0, -_ALTITUDE_STEP_MPS, 0.0),
    "down": (0.0, 0.0, _ALTITUDE_STEP_MPS, 0.0),
    "hold": (0.0, 0.0, 0.0, 0.0),
}


@router.post("/manual-control")
async def send_manual_control(
    payload: ManualControlIn,
    user=Depends(require_user),
):
    """Accept a pilot manual-control command and relay it to the drone.

    The frontend sends start/hold/stop phases per key press.  ``start`` and
    ``hold`` translate to velocity setpoints; ``stop`` sends a zero-velocity
    hold.  ``takeoff`` and ``land`` are handled as discrete one-shot commands.
    """
    orch = await _build_orchestrator()
    drone = getattr(orch, "drone", None)
    if drone is None:
        raise HTTPException(status_code=503, detail="Drone not connected")

    cmd = payload.command
    phase = payload.phase

    if cmd == "takeoff":
        if phase == "stop":
            return {"status": "ignored", "command": cmd, "phase": phase}

        async def _bg_takeoff() -> None:
            try:
                await asyncio.to_thread(drone.arm_and_takeoff, 2.0)
                logger.info("Manual takeoff complete")
            except Exception:
                logger.exception("Manual takeoff failed")

        asyncio.create_task(_bg_takeoff())
        return {"status": "ok", "command": cmd, "detail": "takeoff initiated"}

    if cmd == "land":
        if phase == "stop":
            return {"status": "ignored", "command": cmd, "phase": phase}
        try:
            await asyncio.to_thread(drone.land)
            return {"status": "ok", "command": cmd}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Land failed: {exc}") from exc

    if phase == "stop":
        vel = (0.0, 0.0, 0.0, 0.0)
    else:
        vel = _COMMAND_VELOCITY_MAP.get(cmd, (0.0, 0.0, 0.0, 0.0))

    vx, vy, vz, yaw_rate = vel
    try:
        await asyncio.to_thread(drone.set_mode, "GUIDED")
        await asyncio.to_thread(drone.send_velocity, vx, vy, vz, yaw_rate)
        return {"status": "ok", "command": cmd, "phase": phase}
    except NotImplementedError:
        raise HTTPException(
            status_code=501,
            detail="Active drone adapter does not support velocity commands",
        )
    except (RuntimeError, AttributeError, OSError) as exc:
        raise HTTPException(
            status_code=503, detail=f"Drone link temporarily unavailable: {exc}"
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Velocity command failed: {exc}") from exc
