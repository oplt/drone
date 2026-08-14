from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.core.logging import emit_app_log
from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.modules.identity.dependencies import require_admin, require_user
from backend.modules.identity.models import User
from backend.modules.vehicle_runtime.factory import build_orchestrator as _build_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter(tags=["telemetry"])


@router.post("/start")
async def start_telemetry_stream(user: User = Depends(require_admin)) -> dict[str, Any]:
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
        logger.info(
            "Telemetry stream started",
            extra={"source": "telemetry", "operation": "start"},
        )
        await emit_app_log(
            level="info",
            source="telemetry",
            message="Telemetry stream started",
            details={"connections": telemetry_manager.client_count()},
        )
        return {
            "status": "started",
            "message": "Telemetry stream started successfully",
            "connections": telemetry_manager.client_count(),
        }
    except Exception as e:
        logger.error(
            "Failed to start telemetry stream",
            extra={"source": "telemetry", "operation": "start"},
            exc_info=True,
        )
        await emit_app_log(
            level="error",
            source="telemetry",
            message="Telemetry stream failed to start",
            details={"error": str(e)},
        )
        raise HTTPException(status_code=500, detail=f"Failed to start telemetry: {e!s}") from e


@router.post("/stop")
async def stop_telemetry_stream(user: User = Depends(require_admin)) -> dict[str, Any]:
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
        logger.info(
            "Telemetry stream stopped",
            extra={"source": "telemetry", "operation": "stop"},
        )
        await emit_app_log(
            level="info",
            source="telemetry",
            message="Telemetry stream stopped",
            details={"connections": telemetry_manager.client_count()},
        )
        return {
            "status": "stopped",
            "message": "Telemetry stream stopped successfully",
            "connections": telemetry_manager.client_count(),
        }
    except Exception as e:
        logger.error(
            "Failed to stop telemetry stream",
            extra={"source": "telemetry", "operation": "stop"},
            exc_info=True,
        )
        await emit_app_log(
            level="error",
            source="telemetry",
            message="Telemetry stream failed to stop",
            details={"error": str(e)},
        )
        raise HTTPException(status_code=500, detail=f"Failed to stop telemetry: {e!s}") from e


@router.get("/status")
async def get_telemetry_status(user: User = Depends(require_user)) -> dict[str, Any]:
    """Get current telemetry status"""
    telemetry = telemetry_manager.runtime_snapshot()
    return {
        "running": telemetry["running"],
        "source_connected": telemetry["source_connected"],
        "active_connections": telemetry["active_connections"],
        "last_telemetry_timestamp": telemetry["last_update"],
    }
