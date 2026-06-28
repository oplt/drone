from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from backend.modules.identity.dependencies import OrgUser
from backend.observability.audit import emit_audit_event
from backend.observability.metrics import add as metric_add


def _actor_id(org_user: OrgUser) -> str | None:
    user_id = getattr(org_user.user, "id", None)
    return str(user_id) if user_id is not None else None


def transform_age_ms(locked_at: datetime | None) -> float | None:
    if not isinstance(locked_at, datetime):
        return None
    if locked_at.tzinfo is None:
        locked_at = locked_at.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - locked_at).total_seconds() * 1000.0)


def emit_coordinate_audit(
    *,
    event_name: str,
    action: str,
    resource_type: str,
    resource_id: int | str,
    warehouse_map_id: int,
    org_user: OrgUser,
    reason: str,
    coordinate_frame_id: int | None = None,
    coordinate_frame_version: int | None = None,
    old_value: Any = None,
    new_value: Any = None,
    covariance: list[Any] | None = None,
    transform_age_ms_value: float | None = None,
    validation_result: str = "pass",
    result: Literal["success", "failure"] = "success",
    extra: dict[str, Any] | None = None,
) -> None:
    evidence = {
        "warehouse_map_id": warehouse_map_id,
        "coordinate_frame_id": coordinate_frame_id,
        "coordinate_frame_version": coordinate_frame_version,
        "old_value": old_value,
        "new_value": new_value,
        "covariance": covariance,
        "transform_age_ms": transform_age_ms_value,
        "validation_result": validation_result,
        **(extra or {}),
    }
    emit_audit_event(
        event_name=event_name,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        result=result,
        actor_type="user",
        actor_id=_actor_id(org_user),
        reason=reason,
        extra=evidence,
    )
    metric_add(
        "warehouse_coordinate_audit_events",
        1,
        attrs={"action": action, "result": result, "validation_result": validation_result},
    )
