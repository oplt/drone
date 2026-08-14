"""PointCloud2 parser — safe scalar coercion."""

from __future__ import annotations

import math
from typing import Any


def _safe_int(value: Any, *, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _safe_float(value: Any, *, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _normalise_frame_id(value: Any) -> str | None:
    text = str(value or "").strip()
    return text[:128] or None


__all__ = ["_normalise_frame_id", "_safe_float", "_safe_int"]
