# routes_websocket.py
import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt

from backend.core.database.session import Session
from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.modules.identity.dependencies import get_user_from_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


async def _authorize_websocket(websocket: WebSocket) -> tuple[bool, str | None]:
    """
    Enforce auth for WebSocket connections.
    1. Try Authorization: Bearer header
    2. Try access_token cookie (browser WS upgrade sends cookies automatically)
    Returns (is_authorized, user_id_or_error_message)
    """
    token: str | None = None

    auth = websocket.headers.get("authorization")
    if auth and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1].strip()

    if not token:
        token = websocket.cookies.get("access_token")

    if not token:
        token = websocket.query_params.get("token")

    if not token:
        return False, "Missing authentication token"

    try:
        async with Session() as db:
            user = await get_user_from_token(token, db)
            if not user:
                return False, "Invalid authentication token"
            return True, str(user.id)
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
    Auth via Authorization header or access_token cookie — no query-string token.
    """
    writer_task = None

    is_authorized, user_id_or_error = await _authorize_websocket(websocket)

    if not is_authorized:
        logger.warning(f"Rejecting WebSocket connection: {user_id_or_error}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=user_id_or_error)
        return

    try:
        await websocket.accept()
        logger.info(f"✅ WebSocket connection accepted for user {user_id_or_error}")
    except Exception as e:
        logger.error(f"Failed to accept WebSocket: {e}")
        return

    try:
        writer_task = await telemetry_manager.connect(websocket)

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)

                if message == "ping" or (isinstance(message, str) and '"type":"ping"' in message):
                    try:
                        await websocket.send_text("pong")
                    except Exception:
                        break

            except TimeoutError:
                try:
                    await websocket.send_json({"type": "keepalive", "timestamp": time.time()})
                except Exception:
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
        try:
            if writer_task and not writer_task.done():
                writer_task.cancel()
            telemetry_manager.disconnect(websocket)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
