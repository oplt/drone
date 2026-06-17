from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Any

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from backend.observability import prometheus_metrics
from backend.observability.config import load_config
from backend.observability.database import refresh_pool_metrics
from backend.observability.queue_metrics import refresh_queue_depth_metrics

logger = logging.getLogger(__name__)


def _safe_attrs(attrs: dict[str, Any] | None = None) -> dict[str, str | int | float | bool]:
    safe: dict[str, str | int | float | bool] = {}
    for key, value in (attrs or {}).items():
        if value is None:
            continue
        if isinstance(value, str | int | float | bool):
            safe[key] = value
        else:
            safe[key] = str(value)
    return safe


@lru_cache(maxsize=1)
def _meter():
    from opentelemetry import metrics

    return metrics.get_meter("drone.telemetry")


@lru_cache(maxsize=1)
def _instruments() -> dict[str, Any]:
    meter = _meter()
    return {
        "mavlink_latency": meter.create_histogram(
            "drone.mavlink.command_latency_ms",
            unit="ms",
            description="MAVLink command latency in milliseconds",
        ),
        "mavlink_failures": meter.create_counter(
            "drone.mavlink.command_failures",
            description="MAVLink command failures",
        ),
        "mavlink_retries": meter.create_counter(
            "drone.mavlink.command_retries",
            description="MAVLink command retries",
        ),
        "mavlink_timeouts": meter.create_counter(
            "drone.mavlink.ack_timeouts",
            description="MAVLink ACK timeouts",
        ),
        "ros_messages": meter.create_counter("drone.ros.messages"),
        "ros_callback_latency": meter.create_histogram(
            "drone.ros.callback_latency_ms",
            unit="ms",
        ),
        "ros_topic_stale": meter.create_counter("drone.ros.topic_stale"),
        "ros_message_size": meter.create_histogram(
            "drone.ros.message_size_bytes",
            unit="By",
        ),
        "mapping_frames": meter.create_counter("drone.mapping.frames_received"),
        "mapping_pointclouds": meter.create_counter("drone.mapping.pointclouds_received"),
        "mapping_chunks_generated": meter.create_counter("drone.mapping.chunks_generated"),
        "mapping_chunks_saved": meter.create_counter("drone.mapping.chunks_saved"),
        "mapping_chunk_save_failures": meter.create_counter(
            "drone.mapping.chunk_save_failures"
        ),
        "mapping_chunk_save_latency": meter.create_histogram(
            "drone.mapping.chunk_save_latency_ms",
            unit="ms",
        ),
        "mapping_replay_latency": meter.create_histogram(
            "drone.mapping.replay_latency_ms",
            unit="ms",
        ),
        "video_frames_received": meter.create_counter("drone.video.frames_received"),
        "video_frames_processed": meter.create_counter("drone.video.frames_processed"),
        "video_frames_dropped": meter.create_counter("drone.video.frames_dropped"),
        "video_inference_latency": meter.create_histogram(
            "drone.video.inference_latency_ms",
            unit="ms",
        ),
        "video_detection_count": meter.create_histogram("drone.video.detection_count"),
        "api_websocket_messages": meter.create_counter("drone.api.websocket_messages"),
        "api_websocket_disconnects": meter.create_counter("drone.api.websocket_disconnects"),
        "api_request_failures": meter.create_counter("drone.api.request_failures"),
    }


def add(name: str, value: int | float = 1, attrs: dict[str, Any] | None = None) -> None:
    try:
        _instruments()[name].add(value, _safe_attrs(attrs))
    except Exception:
        return


def record(name: str, value: int | float, attrs: dict[str, Any] | None = None) -> None:
    try:
        _instruments()[name].record(value, _safe_attrs(attrs))
    except Exception:
        return


def setup_metrics(app: Any) -> None:
    """Expose Prometheus metrics without making app startup depend on Prometheus."""

    config = load_config()
    if not config.prometheus_metrics_enabled:
        logger.info("Prometheus metrics disabled by PROMETHEUS_METRICS_ENABLED")
        return
    if getattr(app.state, "prometheus_metrics_instrumented", False):
        return

    @app.middleware("http")
    async def prometheus_metrics_middleware(request: Request, call_next: Any) -> Response:
        route = _route_path(request)
        if route == config.prometheus_metrics_path:
            return await call_next(request)

        method = request.method
        prometheus_metrics.http_requests_in_progress.labels(method=method, route=route).inc()
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed = time.perf_counter() - started_at
            status_code = str(response.status_code)
            _record_http_request(method, route, status_code, elapsed)
            return response
        except Exception as exc:
            elapsed = time.perf_counter() - started_at
            _record_http_request(method, route, "500", elapsed)
            prometheus_metrics.http_exceptions_total.labels(
                method,
                route,
                type(exc).__name__,
            ).inc()
            raise
        finally:
            prometheus_metrics.http_requests_in_progress.labels(method=method, route=route).dec()

    def metrics_endpoint() -> Response:
        try:
            from backend.core.database.session import engine

            refresh_pool_metrics(engine)
        except Exception:
            pass
        refresh_queue_depth_metrics()
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    app.add_api_route(
        config.prometheus_metrics_path,
        metrics_endpoint,
        methods=["GET"],
        include_in_schema=False,
    )
    app.state.prometheus_metrics_instrumented = True


def _record_http_request(method: str, route: str, status_code: str, elapsed: float) -> None:
    prometheus_metrics.http_request_duration_seconds.labels(
        method=method,
        route=route,
        status_code=status_code,
    ).observe(elapsed)
    prometheus_metrics.http_requests_total.labels(
        method=method,
        route=route,
        status_code=status_code,
    ).inc()


def _route_path(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return request.url.path
