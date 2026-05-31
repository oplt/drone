from __future__ import annotations

import time
from typing import TypeVar

T = TypeVar("T")

_last_sensor_ready_at: float | None = None
_last_sensor_ready_payload: dict[str, object] | None = None


def record_sensor_readiness(*, ready: bool, payload: dict[str, object] | None = None) -> None:
    global _last_sensor_ready_at, _last_sensor_ready_payload
    if not ready:
        return
    _last_sensor_ready_at = time.monotonic()
    _last_sensor_ready_payload = payload


def sensor_readiness_recent(*, max_age_s: float = 45.0) -> bool:
    if _last_sensor_ready_at is None:
        return False
    return (time.monotonic() - _last_sensor_ready_at) <= max_age_s


def sensor_readiness_payload() -> dict[str, object] | None:
    return _last_sensor_ready_payload
