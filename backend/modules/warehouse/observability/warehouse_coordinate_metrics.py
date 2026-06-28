from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from backend.observability import prometheus_metrics


def record_tf_lookup_failure(*, source: str) -> None:
    prometheus_metrics.warehouse_tf_lookup_failures_total.labels(source=str(source or "unknown")).inc()


def record_frame_mismatch(*, layer: str) -> None:
    prometheus_metrics.warehouse_frame_mismatch_total.labels(layer=str(layer or "unknown")).inc()


def record_mission_rejection(*, reason: str) -> None:
    prometheus_metrics.warehouse_mission_rejection_total.labels(
        reason=str(reason or "unknown")[:64]
    ).inc()


def record_slam_localization_stale() -> None:
    prometheus_metrics.warehouse_slam_localization_stale_total.inc()


def record_transform_jump(*, source: str) -> None:
    prometheus_metrics.warehouse_transform_jump_total.labels(source=str(source or "unknown")).inc()


@contextmanager
def observe_inspection_validation() -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        prometheus_metrics.warehouse_inspection_validation_duration_seconds.observe(
            max(0.0, time.perf_counter() - started)
        )
