from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from backend.observability import prometheus_metrics


@contextmanager
def profile_stage(stage: str, *, workload: str = "default") -> Iterator[None]:
    """Low-overhead production timing hook; detailed profilers stay opt-in."""
    started = time.perf_counter()
    try:
        yield
    finally:
        prometheus_metrics.profiling_stage_duration_seconds.labels(
            stage=stage, workload=workload
        ).observe(time.perf_counter() - started)
