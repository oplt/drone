"""Live-map flight manifest — JSON coercion helpers."""

from __future__ import annotations

from typing import Any


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, raw in value.items():
        result[str(key)] = max(0, _safe_int(raw, 0))
    return result


def _safe_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _safe_nested_dict(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for key, raw in value.items():
        if isinstance(raw, dict):
            result[str(key)] = dict(raw)
    return result


def _safe_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed == parsed else default


__all__ = [
    "_safe_dict",
    "_safe_dict_list",
    "_safe_float",
    "_safe_int",
    "_safe_nested_dict",
    "_safe_str_list",
]
