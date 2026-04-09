# backend/api/routes_telemetry_control.py
import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.deps import require_admin, require_user
from backend.main import _build_orchestrator
from backend.messaging.websocket import telemetry_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post("/start")
async def start_telemetry_stream(user=Depends(require_admin)):
    """
    Start the WebSocket telemetry stream.
    This should be called when a mission starts.
    """
    if telemetry_manager._running:
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
            "connections": len(telemetry_manager.active_connections),
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
    if not telemetry_manager._running:
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
            "connections": len(telemetry_manager.active_connections),
        }
    except Exception as e:
        logger.error(f"Failed to stop telemetry stream: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop telemetry: {e!s}")


@router.get("/status")
async def get_telemetry_status(user=Depends(require_user)):
    """Get current telemetry status"""
    return {
        "running": telemetry_manager._running,
        "active_connections": len(telemetry_manager.active_connections),
        "last_telemetry_timestamp": telemetry_manager.get_last_telemetry_timestamp(),
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
