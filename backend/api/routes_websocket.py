# routes_websocket.py (corrected)
import json
import time
import asyncio
import logging
from fastapi import WebSocket, WebSocketDisconnect, Query, HTTPException, APIRouter
from typing import Optional
from backend.messaging.websocket import telemetry_manager
from backend.auth.auth import decode_token  # Use decode_token instead of verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


def verify_websocket_token(token: Optional[str] = None) -> dict:
    """Verify WebSocket connection token"""
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # decode_token returns user_id (int) or None
        user_id = decode_token(token)
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")

        return {"user_id": user_id, "sub": str(user_id)}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


@router.websocket("/telemetry")
async def websocket_telemetry(
        websocket: WebSocket,
        token: Optional[str] = Query(None, description="JWT authentication token")
):
    """
    WebSocket endpoint for real-time telemetry data.

    Connect with: ws://localhost:8000/ws/telemetry?token=YOUR_JWT_TOKEN

    The server will broadcast telemetry messages to all connected clients.
    Clients can send 'ping' messages to keep the connection alive.
    """
    try:
        # Verify authentication token if provided
        user_data = None
        if token:
            user_data = verify_websocket_token(token)
            logger.info(f"WebSocket connection from user ID: {user_data.get('user_id', 'unknown')}")

        # Add connection to manager
        await telemetry_manager.connect(websocket)

        # Send initial status
        await websocket.send_json({
            "type": "connection_status",
            "connected": True,
            "authenticated": user_data is not None,
            "timestamp": time.time(),
            "message": "Connected to telemetry stream"
        })

        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for messages from client (with timeout)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)

                try:
                    message = json.loads(data)

                    # Handle ping messages
                    if message.get("type") == "ping":
                        await websocket.send_json({
                            "type": "pong",
                            "timestamp": time.time(),
                            "server_time": time.time()
                        })

                    # Handle subscription requests
                    elif message.get("type") == "subscribe":
                        await websocket.send_json({
                            "type": "subscription_confirmed",
                            "channels": message.get("channels", ["telemetry"]),
                            "timestamp": time.time()
                        })

                    # Handle specific data requests
                    elif message.get("type") == "request_status":
                        await websocket.send_json({
                            "type": "status_update",
                            "connected_clients": len(telemetry_manager.active_connections),
                            "telemetry_running": telemetry_manager._running,
                            "timestamp": time.time()
                        })

                except json.JSONDecodeError:
                    logger.warning(f"Received non-JSON message: {data[:100]}")

            except asyncio.TimeoutError:
                # Send keep-alive ping to client
                try:
                    await websocket.send_json({
                        "type": "ping",
                        "timestamp": time.time()
                    })
                except:
                    break  # Connection is dead

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        telemetry_manager.disconnect(websocket)

    except HTTPException as e:
        logger.warning(f"Authentication failed: {e.detail}")
        try:
            await websocket.close(code=1008, reason=e.detail)  # Policy violation
        except:
            pass

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close(code=1011, reason=f"Server error: {str(e)}")
        except:
            pass
        telemetry_manager.disconnect(websocket)


@router.websocket("/telemetry/public")
async def websocket_telemetry_public(websocket: WebSocket):
    """
    Public WebSocket endpoint for telemetry (no authentication required).
    Use with caution in production.
    """
    try:
        logger.info("New public WebSocket connection")

        # Add to manager
        await telemetry_manager.connect(websocket)

        await websocket.send_json({
            "type": "connection_status",
            "connected": True,
            "public": True,
            "timestamp": time.time(),
            "warning": "Public endpoint - data may be limited"
        })

        # Simple keep-alive loop for public connections
        while True:
            try:
                # Just keep connection open, don't process messages
                await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                # Send periodic keep-alive
                try:
                    await websocket.send_json({
                        "type": "keepalive",
                        "timestamp": time.time()
                    })
                except:
                    break

    except WebSocketDisconnect:
        logger.info("Public WebSocket client disconnected")
        telemetry_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Public WebSocket error: {e}")
        telemetry_manager.disconnect(websocket)


@router.get("/telemetry/status")
async def get_telemetry_status():
    """Get WebSocket telemetry server status"""
    return {
        "status": "running" if telemetry_manager._running else "stopped",
        "active_connections": len(telemetry_manager.active_connections),
        "telemetry_enabled": telemetry_manager._running,
        "last_update": telemetry_manager.last_telemetry.get("timestamp", 0)
    }