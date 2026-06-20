# routes_websocket.py
import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt

from backend.core.database.session import Session
from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.modules.identity.dependencies import get_user_from_token
from backend.modules.identity.models import User
from backend.observability.instruments import observed_span
from backend.observability.metrics import add as metric_add

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


async def _authenticate_websocket(websocket: WebSocket) -> tuple[User | None, str | None]:
    """
    Enforce auth for WebSocket connections.
    1. Try Authorization: Bearer header
    2. Try access_token cookie (browser WS upgrade sends cookies automatically)
    Returns authenticated user or an error message.
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
        return None, "Missing authentication token"

    try:
        async with Session() as db:
            user = await get_user_from_token(token, db)
            if not user:
                return None, "Invalid authentication token"
            return user, None
    except jwt.ExpiredSignatureError:
        return None, "Token expired"
    except JWTError as e:
        logger.warning(f"JWT validation error: {e}")
        return None, "Invalid token"
    except Exception as e:
        logger.error(f"Authorization error: {e}")
        return None, "Authorization failed"


async def _authorize_websocket(websocket: WebSocket) -> tuple[bool, str | None]:
    user, error = await _authenticate_websocket(websocket)
    if user is None:
        return False, error
    return True, str(user.id)


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
        with observed_span("api.websocket.connect", **{"websocket.channel": "telemetry"}):
            writer_task = await telemetry_manager.connect(websocket)

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)

                if message == "ping" or (isinstance(message, str) and '"type":"ping"' in message):
                    try:
                        await websocket.send_text("pong")
                        metric_add("api_websocket_messages", attrs={"message_type": "pong"})
                    except Exception:
                        break

            except TimeoutError:
                try:
                    await websocket.send_json({"type": "keepalive", "timestamp": time.time()})
                    metric_add("api_websocket_messages", attrs={"message_type": "keepalive"})
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
            metric_add("api_websocket_disconnects", attrs={"channel": "telemetry"})
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
