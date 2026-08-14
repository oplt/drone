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


def _websocket_auth_failure_reason(error: str | None) -> str:
    if not error:
        return "unknown"
    if "Query-string" in error:
        return "query_string_token"
    if error == "Missing authentication token":
        return "missing_token"
    if error == "Token expired":
        return "token_expired"
    if error in {"Invalid authentication token", "Invalid token"}:
        return "invalid_token"
    return "authorization_failed"


def _record_websocket_auth_failure(reason: str) -> None:
    from backend.observability import prometheus_metrics

    prometheus_metrics.websocket_auth_failures_total.labels(reason=reason).inc()
    metric_add("api_websocket_auth_failures", attrs={"reason": reason})


async def _authenticate_websocket(websocket: WebSocket) -> tuple[User | None, str | None]:
    """
    Enforce auth for WebSocket connections.
    1. Try Authorization: Bearer header
    2. Try access_token cookie (browser WS upgrade sends cookies automatically)
    Query-string tokens are rejected (leak via logs/proxies).
    Returns authenticated user or an error message.
    """
    if websocket.query_params.get("token"):
        reason = "query_string_token"
        _record_websocket_auth_failure(reason)
        return None, "Query-string tokens are not allowed; use Authorization header or cookie"

    token: str | None = None

    auth = websocket.headers.get("authorization")
    if auth and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1].strip()

    if not token:
        token = websocket.cookies.get("access_token")

    if not token:
        _record_websocket_auth_failure("missing_token")
        return None, "Missing authentication token"

    try:
        async with Session() as db:
            user = await get_user_from_token(token, db)
            if not user:
                _record_websocket_auth_failure("invalid_token")
                return None, "Invalid authentication token"
            return user, None
    except jwt.ExpiredSignatureError:
        _record_websocket_auth_failure("token_expired")
        return None, "Token expired"
    except JWTError as e:
        logger.warning(f"JWT validation error: {e}")
        _record_websocket_auth_failure("invalid_token")
        return None, "Invalid token"
    except Exception as e:
        logger.error(f"Authorization error: {e}")
        _record_websocket_auth_failure("authorization_failed")
        return None, "Authorization failed"


@router.websocket("/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """
    Protected WebSocket endpoint for telemetry.
    Auth via Authorization header or access_token cookie — no query-string token.
    Optional client messages: {"type":"subscribe","mission_runtime_id":"..."} to scope fan-out.
    """
    writer_task = None

    user, auth_error = await _authenticate_websocket(websocket)
    if user is None:
        logger.warning(f"Rejecting WebSocket connection: {auth_error}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=auth_error)
        return

    try:
        await websocket.accept()
        logger.info("✅ WebSocket connection accepted for user %s org=%s", user.id, user.org_id)
    except Exception as e:
        logger.error(f"Failed to accept WebSocket: {e}")
        return

    try:
        with observed_span("api.websocket.connect", **{"websocket.channel": "telemetry"}):
            writer_task = await telemetry_manager.connect(
                websocket,
                user_id=int(user.id),
                org_id=int(user.org_id) if user.org_id is not None else None,
            )

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)

                if message == "ping" or (isinstance(message, str) and '"type":"ping"' in message):
                    try:
                        await websocket.send_text("pong")
                        metric_add("api_websocket_messages", attrs={"message_type": "pong"})
                    except Exception:
                        break
                    continue

                try:
                    import orjson

                    parsed = orjson.loads(message)
                except Exception:
                    parsed = None
                if isinstance(parsed, dict) and parsed.get("type") == "subscribe":
                    mission_runtime_id = parsed.get("mission_runtime_id")
                    wire_protocol = parsed.get("protocol") or parsed.get("wire_protocol")
                    telemetry_manager.set_client_subscription(
                        websocket,
                        mission_runtime_id=str(mission_runtime_id)
                        if mission_runtime_id
                        else None,
                        wire_protocol=str(wire_protocol).lower()
                        if isinstance(wire_protocol, str)
                        else None,
                    )
                    try:
                        await websocket.send_json(
                            {
                                "type": "subscribed",
                                "mission_runtime_id": mission_runtime_id,
                                "protocol": wire_protocol or "legacy",
                            }
                        )
                    except Exception:
                        break

            except TimeoutError:
                try:
                    await websocket.send_json({"type": "keepalive", "timestamp": time.time()})
                    metric_add("api_websocket_messages", attrs={"message_type": "keepalive"})
                except Exception:
                    break

            except WebSocketDisconnect:
                logger.info("WebSocket client disconnected for user %s", user.id)
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
