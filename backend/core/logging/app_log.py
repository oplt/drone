from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

AppLogLevel = Literal["debug", "info", "warn", "error", "critical"]
AppLogSource = Literal[
    "backend",
    "frontend",
    "drone",
    "mavlink",
    "telemetry",
    "mission",
    "video",
    "analysis",
    "model",
    "upload",
    "websocket",
    "api",
]

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "key",
)
_MAX_DETAIL_DEPTH = 3
_MAX_STRING_LEN = 500

logger = logging.getLogger(__name__)


class AppLogEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    level: AppLogLevel
    source: AppLogSource
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    mission_id: str | None = None
    flight_id: str | None = None

    def websocket_message(self) -> dict[str, Any]:
        return {"type": "app_log", "data": self.model_dump(mode="json", exclude_none=True)}


def sanitize_log_details(value: Any, *, _depth: int = 0) -> Any:
    if _depth >= _MAX_DETAIL_DEPTH:
        return str(value)[:_MAX_STRING_LEN]
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, raw in value.items():
            key_s = str(key)
            if any(part in key_s.lower() for part in _SENSITIVE_KEY_PARTS):
                sanitized[key_s] = "[redacted]"
            else:
                sanitized[key_s] = sanitize_log_details(raw, _depth=_depth + 1)
        return sanitized
    if isinstance(value, (list, tuple, set)):
        return [sanitize_log_details(item, _depth=_depth + 1) for item in list(value)[:25]]
    if isinstance(value, bytes):
        return f"[{len(value)} bytes]"
    if isinstance(value, str):
        return value if len(value) <= _MAX_STRING_LEN else f"{value[:_MAX_STRING_LEN]}..."
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:_MAX_STRING_LEN]


async def emit_app_log(
    *,
    level: AppLogLevel,
    source: AppLogSource,
    message: str,
    details: Mapping[str, Any] | None = None,
    request_id: str | None = None,
    mission_id: str | None = None,
    flight_id: str | int | None = None,
) -> AppLogEvent:
    event = AppLogEvent(
        level=level,
        source=source,
        message=message,
        details=sanitize_log_details(dict(details or {})),
        request_id=request_id,
        mission_id=mission_id,
        flight_id=str(flight_id) if flight_id is not None else None,
    )
    try:
        from backend.infrastructure.messaging.websocket_publisher import telemetry_manager

        await telemetry_manager.broadcast(event.websocket_message())
    except Exception:
        logger.debug("Failed to broadcast app log event", exc_info=True)
    return event
