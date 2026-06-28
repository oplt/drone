"""Structured audit logging for state-changing operations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from backend.observability.context import log_context_fields

logger = logging.getLogger("audit")

Result = Literal["success", "failure"]
_SENSITIVE_KEYS = {"authorization", "cookie", "password", "secret", "token"}


def _safe_audit_value(value: Any, *, depth: int = 0) -> Any:
    """Keep useful structured evidence while bounding size and removing secrets."""
    if depth > 4:
        return "[max_depth]"
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, item in list(value.items())[:50]:
            key = str(raw_key)[:100]
            if any(sensitive in key.lower() for sensitive in _SENSITIVE_KEYS):
                result[key] = "[redacted]"
            else:
                result[key] = _safe_audit_value(item, depth=depth + 1)
        return result
    if isinstance(value, list | tuple):
        return [_safe_audit_value(item, depth=depth + 1) for item in value[:100]]
    return str(value)[:500]


def emit_audit_event(
    *,
    event_name: str,
    action: str,
    resource_type: str,
    result: Result,
    actor_type: str = "system",
    actor_id: str | None = None,
    resource_id: str | None = None,
    reason: str | None = None,
    error_type: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit a structured JSON audit record without secrets or PII."""

    payload: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event_name": event_name,
        "actor_type": actor_type,
        "action": action,
        "resource_type": resource_type,
        "result": result,
        **log_context_fields(),
    }
    if actor_id:
        payload["actor_id"] = actor_id
    if resource_id:
        payload["resource_id"] = resource_id
    if reason:
        payload["reason"] = reason[:500]
    if result == "failure" and error_type:
        payload["error_type"] = error_type
    if extra:
        for key, value in extra.items():
            if value is None:
                continue
            payload[str(key)[:100]] = _safe_audit_value(value)
    logger.info(event_name, extra=payload)
