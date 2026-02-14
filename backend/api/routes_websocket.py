# routes_websocket.py (FIXED VERSION)
import time
import asyncio
import logging
from fastapi import WebSocket, WebSocketDisconnect, WebSocketException, status
from fastapi import APIRouter, Depends
from backend.messaging.websocket import telemetry_manager
from backend.auth.deps import get_user_from_token
from backend.db.session import Session
from jose import jwt, JWTError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


async def _authorize_websocket(websocket: WebSocket) -> tuple[bool, str | None]:
    """
    Enforce auth for WebSocket connections.
    Returns (is_authorized, user_id_or_error_message)
    """
    # Get token from query parameters or headers
    token = websocket.query_params.get("token")

    if not token:
        auth = websocket.headers.get("authorization")
        if auth and auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1].strip()

    if not token:
        return False, "Missing authentication token"

    try:
        async with Session() as db:
            user = await get_user_from_token(token, db)
            if not user:
                return False, "Invalid authentication token"
            return True, user.id
    except jwt.ExpiredSignatureError:
        return False, "Token expired"
    except JWTError as e:
        logger.warning(f"JWT validation error: {e}")
        return False, "Invalid token"
    except Exception as e:
        logger.error(f"Authorization error: {e}")
        return False, "Authorization failed"


@router.websocket("/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """
    Protected WebSocket endpoint for telemetry.
    """
    writer_task = None

    # First, validate token BEFORE accepting connection
    is_authorized, user_id_or_error = await _authorize_websocket(websocket)

    if not is_authorized:
        logger.warning(f"Rejecting WebSocket connection: {user_id_or_error}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=user_id_or_error)
        return

    # Now accept the connection
    try:
        await websocket.accept()
        logger.info(f"✅ WebSocket connection accepted for user {user_id_or_error}")
    except Exception as e:
        logger.error(f"Failed to accept WebSocket: {e}")
        return

    try:
        # Register with telemetry manager
        writer_task = await telemetry_manager.connect(websocket)

        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for messages with timeout
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)

                # Handle ping/pong
                if message == "ping" or (isinstance(message, str) and '"type":"ping"' in message):
                    try:
                        await websocket.send_text("pong")
                    except:
                        break

            except asyncio.TimeoutError:
                # Send keepalive
                try:
                    await websocket.send_json({"type": "keepalive", "timestamp": time.time()})
                except:
                    break

            except WebSocketDisconnect:
                logger.info(f"WebSocket client disconnected for user {user_id_or_error}")
                break

            except Exception as e:
                logger.error(f"WebSocket message error: {e}")
                break

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Cleanup
        try:
            if writer_task and not writer_task.done():
                writer_task.cancel()
            telemetry_manager.disconnect(websocket)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")