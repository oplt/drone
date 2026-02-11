# backend/api/routes_telemetry_control.py
import logging
from fastapi import APIRouter, HTTPException
from backend.messaging.websocket import telemetry_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post("/start")
async def start_telemetry_stream():
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
        telemetry_manager.start_telemetry_stream()
        return {
            "status": "started",
            "message": "Telemetry stream started successfully",
            "connections": len(telemetry_manager.active_connections),
        }
    except Exception as e:
        logger.error(f"Failed to start telemetry stream: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to start telemetry: {str(e)}"
        )


@router.post("/stop")
async def stop_telemetry_stream():
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
        telemetry_manager.stop_telemetry_stream()
        return {
            "status": "stopped",
            "message": "Telemetry stream stopped successfully",
            "connections": len(telemetry_manager.active_connections),
        }
    except Exception as e:
        logger.error(f"Failed to stop telemetry stream: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to stop telemetry: {str(e)}"
        )


@router.get("/status")
async def get_telemetry_status():
    """Get current telemetry status"""
    return {
        "running": telemetry_manager._running,
        "active_connections": len(telemetry_manager.active_connections),
        "last_telemetry_timestamp": telemetry_manager.last_telemetry.get(
            "timestamp", 0
        ),
    }
