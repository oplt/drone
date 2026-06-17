"""Structured audit logging for state-changing operations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from backend.observability.context import log_context_fields

logger = logging.getLogger("audit")

Result = Literal["success", "failure"]


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
    if result == "failure":
        if reason:
            payload["reason"] = reason[:500]
        if error_type:
            payload["error_type"] = error_type
    if extra:
        for key, value in extra.items():
            if value is None:
                continue
            if isinstance(value, str | int | float | bool):
                payload[key] = value if not isinstance(value, str) else value[:500]
    logger.info(event_name, extra=payload)
