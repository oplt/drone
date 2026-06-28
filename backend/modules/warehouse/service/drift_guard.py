from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import WarehouseInspectionMission
from backend.observability.metrics import add as metric_add

logger = logging.getLogger(__name__)


def transform_checksum(transform: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(transform, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_localization_evidence(
    *,
    transform: dict[str, Any],
    transform_timestamp: datetime,
    max_age_s: float,
    covariance: list[float],
    confidence: float,
    now: datetime | None = None,
    min_confidence: float = 0.5,
    max_position_std_m: float = 1.0,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    if transform_timestamp.tzinfo is None:
        transform_timestamp = transform_timestamp.replace(tzinfo=UTC)
    age_s = (now - transform_timestamp).total_seconds()
    if age_s < -1.0:
        raise ValueError("transform timestamp cannot be in the future")
    if not math.isfinite(max_age_s) or max_age_s <= 0 or age_s > max_age_s:
        raise ValueError(f"transform is stale: age={age_s:.3f}s maximum={max_age_s:.3f}s")
    if len(covariance) != 36 or not all(math.isfinite(float(value)) for value in covariance):
        raise ValueError("locked transform requires a finite row-major 6x6 covariance")
    position_variances = [float(covariance[index]) for index in (0, 7, 14)]
    if any(value < 0 for value in position_variances):
        raise ValueError("position covariance diagonal must be non-negative")
    max_std_m = math.sqrt(max(position_variances))
    if max_std_m > max_position_std_m:
        raise ValueError(
            f"position covariance is too uncertain: std={max_std_m:.3f}m "
            f"maximum={max_position_std_m:.3f}m"
        )
    if not math.isfinite(confidence) or confidence < min_confidence or confidence > 1.0:
        raise ValueError(f"localization confidence must be in [{min_confidence}, 1.0]")
    return {
        "age_s": max(0.0, age_s),
        "max_position_std_m": max_std_m,
        "confidence": confidence,
        "checksum_sha256": transform_checksum(transform),
    }


def validate_scale_calibration(
    *,
    scale: float,
    map_resolution_m: float | None,
    expected_distance_m: float | None,
    measured_distance_m: float | None,
    max_relative_error: float = 0.02,
) -> dict[str, Any]:
    if not math.isclose(float(scale), 1.0, abs_tol=1e-9):
        raise ValueError("warehouse map scale must be exactly 1.0 metre per metre")
    if map_resolution_m is not None and (
        not math.isfinite(map_resolution_m) or map_resolution_m <= 0
    ):
        raise ValueError("map_resolution_m must be a positive finite metre value")
    if (expected_distance_m is None) != (measured_distance_m is None):
        raise ValueError("known-distance calibration requires expected and measured distances")
    evidence: dict[str, Any] = {}
    if expected_distance_m is not None and measured_distance_m is not None:
        if expected_distance_m <= 0 or measured_distance_m <= 0:
            raise ValueError("known calibration distances must be positive")
        relative_error = abs(measured_distance_m - expected_distance_m) / expected_distance_m
        if relative_error > max_relative_error:
            raise ValueError(
                f"known-distance scale error {relative_error:.2%} exceeds {max_relative_error:.2%}"
            )
        evidence = {
            "expected_distance_m": expected_distance_m,
            "measured_distance_m": measured_distance_m,
            "relative_error": relative_error,
        }
    return evidence


async def ensure_no_active_missions_for_frame_change(
    db: AsyncSession, *, warehouse_map_id: int
) -> None:
    count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(WarehouseInspectionMission)
                .where(
                    WarehouseInspectionMission.warehouse_map_id == warehouse_map_id,
                    WarehouseInspectionMission.status.in_(("planned", "running")),
                )
            )
        ).scalar_one()
    )
    if count:
        raise HTTPException(
            409,
            f"Coordinate revision is frozen by {count} planned/running warehouse mission(s)",
        )


@dataclass(frozen=True)
class TransformDelta:
    translation_m: float
    yaw_rad: float
    jumped: bool


class TransformDriftMonitor:
    def __init__(self, *, max_translation_jump_m: float = 0.5, max_yaw_jump_rad: float = 0.35):
        self.max_translation_jump_m = float(max_translation_jump_m)
        self.max_yaw_jump_rad = float(max_yaw_jump_rad)
        self._last: dict[str, tuple[tuple[float, float, float], float]] = {}
        self._lock = threading.Lock()

    def observe(self, source: str, transform: Any) -> TransformDelta | None:
        translation = transform.transform.translation
        rotation = transform.transform.rotation
        point = (float(translation.x), float(translation.y), float(translation.z))
        yaw = math.atan2(
            2 * (float(rotation.w) * float(rotation.z) + float(rotation.x) * float(rotation.y)),
            1 - 2 * (float(rotation.y) ** 2 + float(rotation.z) ** 2),
        )
        with self._lock:
            previous = self._last.get(source)
            self._last[source] = (point, yaw)
        if previous is None:
            return None
        translation_delta = math.dist(previous[0], point)
        yaw_delta = abs((yaw - previous[1] + math.pi) % (2 * math.pi) - math.pi)
        jumped = (
            translation_delta > self.max_translation_jump_m
            or yaw_delta > self.max_yaw_jump_rad
        )
        logger.info(
            "warehouse_map_odom_delta",
            extra={
                "source": source,
                "translation_delta_m": translation_delta,
                "yaw_delta_rad": yaw_delta,
                "jumped": jumped,
            },
        )
        if jumped:
            logger.error(
                "warehouse_transform_jump_alarm",
                extra={
                    "source": source,
                    "translation_delta_m": translation_delta,
                    "yaw_delta_rad": yaw_delta,
                },
            )
            metric_add("warehouse_transform_jump_alarms", attrs={"source": source})
            try:
                from backend.modules.warehouse.service.slam_localization_monitor import (
                    on_transform_jump,
                )

                on_transform_jump(source=source)
            except Exception:
                pass
        return TransformDelta(translation_delta, yaw_delta, jumped)


warehouse_transform_drift_monitor = TransformDriftMonitor()
