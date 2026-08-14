from __future__ import annotations

from backend.observability import prometheus_metrics


def _record_telemetry_redis_fallback(reason: str) -> None:
    prometheus_metrics.telemetry_redis_fallback_total.labels(reason=reason).inc()
