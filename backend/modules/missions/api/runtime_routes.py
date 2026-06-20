from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.modules.missions.application import mission_application
from backend.modules.vehicle_runtime.factory import get_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter()


def _timestamp(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    return float(value or fallback)


async def _active_runtime_payload(row: Any, orchestrator: Any) -> dict[str, Any]:
    flight_id = row.flight_id
    if flight_id is None:
        raw_flight_id = getattr(orchestrator, "_flight_id", None)
        try:
            flight_id = int(raw_flight_id) if raw_flight_id is not None else None
        except (TypeError, ValueError):
            flight_id = None
        if flight_id is not None:
            await mission_application.set_flight_id(
                row.client_flight_id,
                flight_id=flight_id,
            )
    private_task = getattr(row, "private_patrol_task_type", None)
    return {
        "flight_id": row.client_flight_id,
        "mission_name": row.mission_name,
        "mission_type": row.mission_type,
        "mission_task_type": private_task or row.mission_task_type,
        "state": row.state,
        "created_at": _timestamp(row.created_at),
        "updated_at": _timestamp(row.updated_at, _timestamp(row.created_at)),
        "preflight_run_id": row.preflight_run_uuid,
        "db_flight_id": str(flight_id) if flight_id is not None else None,
        "last_error": row.failure_reason,
    }


@router.get("/flight/status")
async def get_flight_status() -> dict[str, Any]:
    try:
        runtime_payload = None
        active_row = await mission_application.get_active()
        orchestrator = None
        if active_row is not None:
            orchestrator = await get_orchestrator()
            runtime_payload = await _active_runtime_payload(active_row, orchestrator)

        telemetry = telemetry_manager.runtime_snapshot()
        position = telemetry_manager.latest_position_snapshot()
        state = runtime_payload["state"] if runtime_payload else None
        return {
            "flight_id": runtime_payload["flight_id"] if runtime_payload else None,
            "mission_name": runtime_payload["mission_name"]
            if runtime_payload
            else "No active mission",
            "telemetry": {
                "running": telemetry["running"],
                "source_connected": telemetry["source_connected"],
                "active_connections": telemetry["active_connections"],
                "has_position_data": position["has_position"],
                "last_update": telemetry["last_update"],
                "position": position["position"],
            },
            "orchestrator": {
                "ready": orchestrator is not None,
                "has_drone": orchestrator is not None
                and getattr(orchestrator, "drone", None) is not None,
                "drone_connected": bool(
                    telemetry["source_connected"]
                    or (
                        orchestrator is not None
                        and getattr(orchestrator, "drone", None) is not None
                    )
                ),
            },
            "mission_lifecycle": runtime_payload,
            "command_capabilities": {
                "pause": state in {"airborne", "running"},
                "resume": state == "paused",
                "abort": state in {"queued", "arming", "airborne", "running", "paused", "resumed"},
            },
        }
    except Exception as exc:
        logger.exception("get_flight_status failed")
        telemetry = telemetry_manager.runtime_snapshot()
        return {
            "error": str(exc),
            "telemetry": {
                "running": telemetry["running"],
                "source_connected": telemetry["source_connected"],
                "active_connections": telemetry["active_connections"],
                "last_update": telemetry["last_update"],
            },
        }


@router.get("/drone/position")
async def get_drone_position() -> dict[str, Any]:
    telemetry = telemetry_manager.runtime_snapshot()
    snapshot = telemetry_manager.latest_position_snapshot()
    position = snapshot["position"]
    return {
        "has_position": snapshot["has_position"],
        "lat": position["lat"],
        "lng": position["lon"],
        "alt": position["alt"],
        "relative_alt": position["relative_alt"],
        "timestamp": telemetry["last_update"],
    }


@router.post("/telemetry/start")
async def start_telemetry() -> dict[str, str]:
    if telemetry_manager.runtime_snapshot()["running"]:
        return {"status": "already_running", "message": "Telemetry already running"}
    try:
        await (await get_orchestrator()).start_live_telemetry()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start telemetry: {exc}") from exc
    return {"status": "started", "message": "Telemetry stream started"}


@router.post("/telemetry/stop")
async def stop_telemetry() -> dict[str, str]:
    if not telemetry_manager.runtime_snapshot()["running"]:
        return {"status": "already_stopped", "message": "Telemetry already stopped"}
    try:
        await (await get_orchestrator()).stop_live_telemetry()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to stop telemetry: {exc}") from exc
    return {"status": "stopped", "message": "Telemetry stream stopped"}
