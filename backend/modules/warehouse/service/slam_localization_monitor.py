from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any

from backend.modules.warehouse.observability.warehouse_coordinate_metrics import (
    record_slam_localization_stale,
    record_transform_jump,
)


@dataclass
class SlamLocalizationState:
    confidence: float = 0.0
    age_ms: float = 0.0
    updated_at_monotonic: float = 0.0
    transform: dict[str, Any] | None = None


_LOCK = threading.Lock()
_STATE = SlamLocalizationState()


def update_slam_localization(
    *,
    confidence: float,
    transform: dict[str, Any] | None = None,
) -> None:
    now = time.monotonic()
    with _LOCK:
        _STATE.confidence = max(0.0, min(1.0, float(confidence)))
        _STATE.transform = transform
        _STATE.updated_at_monotonic = now
        _STATE.age_ms = 0.0


def slam_localization_snapshot(*, max_age_ms: float = 1500.0, min_confidence: float = 0.5) -> dict[str, Any]:
    now = time.monotonic()
    with _LOCK:
        age_ms = max(0.0, (now - _STATE.updated_at_monotonic) * 1000.0) if _STATE.updated_at_monotonic else 1e9
        confidence = float(_STATE.confidence)
        transform = _STATE.transform
    healthy = age_ms <= float(max_age_ms) and confidence >= float(min_confidence)
    if not healthy:
        record_slam_localization_stale()
    return {
        "healthy": healthy,
        "confidence": confidence,
        "age_ms": age_ms,
        "transform": transform,
    }


def validate_slam_localization_for_execution(
    *,
    max_age_ms: float = 1500.0,
    min_confidence: float = 0.5,
) -> None:
    snapshot = slam_localization_snapshot(max_age_ms=max_age_ms, min_confidence=min_confidence)
    if snapshot["healthy"]:
        return
    raise ValueError(
        "SLAM localization is stale or low-confidence: "
        f"age_ms={snapshot['age_ms']:.0f} confidence={snapshot['confidence']:.2f}"
    )


def ingest_slam_status_message(payload: str | bytes) -> None:
    try:
        body = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return
    if not isinstance(body, dict):
        return
    update_slam_localization(
        confidence=float(body.get("confidence") or 0.0),
        transform=body.get("transform") if isinstance(body.get("transform"), dict) else None,
    )


def on_transform_jump(*, source: str) -> None:
    record_transform_jump(source=source)
