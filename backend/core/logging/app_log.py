from __future__ import annotations

import asyncio
import logging
import re
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

_SENSITIVE_TOKENS = {
    "authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "key",
    "credential",
    "credentials",
}
_MAX_DETAIL_DEPTH = 3
_MAX_STRING_LEN = 500
_MAX_MAPPING_ITEMS = 80
_MAX_SEQUENCE_ITEMS = 50
_BROADCAST_TIMEOUT_S = 1.0

_KEY_SPLIT_RE = re.compile(r"[^a-z0-9]+")
logger = logging.getLogger(__name__)


class AppLogEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    level: AppLogLevel
    source: AppLogSource
    message: str = Field(max_length=1000)
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    mission_id: str | None = None
    flight_id: str | None = None

    def websocket_message(self) -> dict[str, Any]:
        return {"type": "app_log", "data": self.model_dump(mode="json", exclude_none=True)}


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized in _SENSITIVE_TOKENS:
        return True
    parts = {part for part in _KEY_SPLIT_RE.split(normalized) if part}
    if parts & _SENSITIVE_TOKENS:
        return True
    return normalized.endswith(("_token", "_secret", "_password", "_api_key", ".token"))


def sanitize_log_details(value: Any, *, _depth: int = 0) -> Any:
    if _depth >= _MAX_DETAIL_DEPTH:
        return str(value)[:_MAX_STRING_LEN]
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for index, (key, raw) in enumerate(value.items()):
            if index >= _MAX_MAPPING_ITEMS:
                sanitized["__truncated__"] = True
                break
            key_s = str(key)
            if _is_sensitive_key(key_s):
                sanitized[key_s] = "[redacted]"
            else:
                sanitized[key_s] = sanitize_log_details(raw, _depth=_depth + 1)
        return sanitized
    if isinstance(value, (list, tuple, set)):
        return [
            sanitize_log_details(item, _depth=_depth + 1)
            for item in list(value)[:_MAX_SEQUENCE_ITEMS]
        ]
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
        message=str(message)[:1000],
        details=sanitize_log_details(dict(details or {})),
        request_id=request_id,
        mission_id=mission_id,
        flight_id=str(flight_id) if flight_id is not None else None,
    )
    try:
        from backend.infrastructure.messaging.websocket_publisher import telemetry_manager

        await asyncio.wait_for(
            telemetry_manager.broadcast(event.websocket_message()),
            timeout=_BROADCAST_TIMEOUT_S,
        )
    except Exception:
        logger.debug("Failed to broadcast app log event", exc_info=True)
    return event
