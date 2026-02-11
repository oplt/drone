# routes_websocket.py (SIMPLIFIED VERSION)
import time
import asyncio
import logging
from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from backend.messaging.websocket import telemetry_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/telemetry/public")
async def websocket_telemetry_public(websocket: WebSocket):
    """
    Public WebSocket endpoint for telemetry (no authentication required).
    """
    writer_task = None
    try:
        # Accept the connection
        await websocket.accept()
        logger.info("✅ New public WebSocket connection accepted")

        # Let the manager handle the connection setup
        writer_task = await telemetry_manager.connect(websocket)

        # Keep the connection alive
        try:
            while True:
                # Try to receive a message (with timeout)
                try:
                    data = await asyncio.wait_for(
                        websocket.receive_text(), timeout=30.0
                    )

                    # Handle ping messages
                    if data.strip() == "ping":
                        await websocket.send_text("pong")

                except asyncio.TimeoutError:
                    # Send keep-alive
                    try:
                        await websocket.send_json(
                            {"type": "keepalive", "timestamp": time.time()}
                        )
                    except:
                        break  # Connection closed

        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected normally")

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Ensure cleanup
        try:
            if writer_task and not writer_task.done():
                writer_task.cancel()
            telemetry_manager.disconnect(websocket)
        except:
            pass


@router.get("/telemetry/status")
async def get_telemetry_status():
    """Get WebSocket telemetry server status"""
    return {
        "status": "running" if telemetry_manager._running else "stopped",
        "active_connections": len(telemetry_manager.active_connections),
        "telemetry_enabled": telemetry_manager._running,
        "last_update": telemetry_manager.last_telemetry.get("timestamp", 0),
    }


@router.get("/debug/connections")
async def debug_websocket_connections():
    """
    Debug endpoint to monitor WebSocket connections.
    """
    from backend.messaging.websocket import telemetry_manager

    client_info = []
    try:
        with telemetry_manager._lock:
            for websocket, client in telemetry_manager._clients.items():
                client_info.append(
                    {
                        "websocket_id": str(id(websocket)),
                        "client": {
                            "host": getattr(client, "client_host", None),
                            "port": getattr(client, "client_port", None),
                            "user_agent": getattr(client, "user_agent", None),
                        },
                        "connected_time": getattr(client, "connected_time", 0),
                        "connection_duration": time.time()
                        - getattr(client, "connected_time", time.time()),
                        "queue_size": client.q.qsize() if hasattr(client, "q") else 0,
                        "task_running": not client.task.done()
                        if hasattr(client, "task") and client.task
                        else False,
                    }
                )
    except Exception as e:
        logger.error(f"Error getting client info: {e}")

    return {
        "active_connections": len(telemetry_manager.active_connections),
        "telemetry_running": telemetry_manager._running,
        "telemetry_thread_alive": telemetry_manager._telemetry_thread.is_alive()
        if telemetry_manager._telemetry_thread
        else False,
        "clients": client_info,
        "mavlink_connected": telemetry_manager.mav_conn is not None,
        "last_telemetry": {
            "timestamp": telemetry_manager.last_telemetry.get("timestamp", 0),
            "age": time.time() - telemetry_manager.last_telemetry.get("timestamp", 0),
            "has_position": bool(
                telemetry_manager.last_telemetry.get("position", {}).get("lat", 0)
                or telemetry_manager.last_telemetry.get("position", {}).get("lon", 0)
            ),
            "position": telemetry_manager.last_telemetry.get("position", {}),
        },
    }
