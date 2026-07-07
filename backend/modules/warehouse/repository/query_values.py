from __future__ import annotations

from typing import Any

from backend.modules.warehouse.repository.contracts import WarehouseRepositoryError

MAX_LIST_LIMIT = 500


def clamp_list_limit(
    limit: int,
    *,
    default: int,
    max_limit: int = MAX_LIST_LIMIT,
) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = default
    return max(1, min(max_limit, value))


def require_json_object(value: dict[str, Any] | None, *, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise WarehouseRepositoryError(f"{field_name} must be a JSON object.")
    return dict(value)
