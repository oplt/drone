from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import numpy as np
import pytest


def test_setup_observability_does_not_crash_without_maple(monkeypatch):
    from backend.observability import otel

    monkeypatch.setattr(otel, "_configured", False)
    monkeypatch.setenv("OBSERVABILITY_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    otel.setup_observability(app=None, service_name="drone-api")


def test_setup_observability_disabled_does_not_crash(monkeypatch):
    from backend.observability import otel

    monkeypatch.setattr(otel, "_configured", False)
    monkeypatch.setenv("OBSERVABILITY_ENABLED", "false")
    otel.setup_observability(app=None, service_name="drone-api")


def test_setup_observability_idempotent_fastapi(monkeypatch):
    from fastapi import FastAPI

    from backend.observability import otel

    app = FastAPI()
    monkeypatch.setattr(otel, "_configured", False)
    monkeypatch.setattr(otel, "_setup_traces", lambda *args, **kwargs: None)
    monkeypatch.setattr(otel, "_setup_library_instrumentation", lambda: None)
    monkeypatch.setenv("OBSERVABILITY_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")

    class FakeFastAPIInstrumentor:
        calls: ClassVar[list[FastAPI]] = []

        @classmethod
        def instrument_app(cls, target_app):
            cls.calls.append(target_app)

    import opentelemetry.instrumentation.fastapi as fastapi_instrumentation

    monkeypatch.setattr(
        fastapi_instrumentation,
        "FastAPIInstrumentor",
        FakeFastAPIInstrumentor,
    )
    otel.setup_observability(app=app, service_name="drone-api")
    otel.setup_observability(app=app, service_name="drone-api")

    assert FakeFastAPIInstrumentor.calls == [app]
    assert app.state.otel_instrumented is True


def test_metrics_endpoint_exposes_prometheus_text(monkeypatch):
    from fastapi import FastAPI

    from backend.observability.metrics import setup_metrics

    monkeypatch.setenv("PROMETHEUS_METRICS_ENABLED", "true")
    app = FastAPI()
    setup_metrics(app)

    route = next(route for route in app.routes if getattr(route, "path", "") == "/metrics")
    response = route.endpoint()

    assert "text/plain" in response.media_type
    assert b"python_info" in response.body


def test_signal_endpoint_accepts_maple_base_or_full_endpoint():
    from backend.observability.otel import _signal_endpoint

    assert (
        _signal_endpoint("metrics", "http://127.0.0.1:4318")
        == "http://127.0.0.1:4318/v1/metrics"
    )
    assert (
        _signal_endpoint("logs", "http://127.0.0.1:4318/v1/traces")
        == "http://127.0.0.1:4318/v1/logs"
    )


def test_otlp_headers_decode_grafana_cloud_basic_auth(monkeypatch):
    from backend.observability import otel

    monkeypatch.setattr(otel.settings, "otel_exporter_otlp_headers", "")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Basic%20abc123")

    assert otel._otlp_headers() == {"Authorization": "Basic abc123"}


def test_resource_attributes_include_grafana_grouping(monkeypatch):
    from backend.observability import otel

    monkeypatch.setattr(otel.settings, "otel_resource_attributes", "")
    monkeypatch.setenv(
        "OTEL_RESOURCE_ATTRIBUTES",
        "service.namespace=drone,service.version=test",
    )

    attrs = otel._resource_attributes()
    assert attrs["service.namespace"] == "drone"
    assert attrs["service.version"] == "test"


def test_observed_span_records_exception_and_reraises(monkeypatch):
    from opentelemetry import trace

    from backend.observability import instruments

    captured = SimpleNamespace(recorded=None, status=None)

    class FakeSpan:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def record_exception(self, exc):
            captured.recorded = exc

        def set_status(self, status):
            captured.status = status

        def set_attribute(self, key, value):
            return None

    class FakeTracer:
        def start_as_current_span(self, name, attributes=None):
            return FakeSpan()

    monkeypatch.setattr(trace, "get_tracer", lambda _name: FakeTracer())

    with pytest.raises(ValueError) as exc_info:
        with instruments.observed_span("test.span", mission_id="m1"):
            raise ValueError("boom")

    assert captured.recorded is exc_info.value
    assert captured.status is not None


def test_mavlink_command_long_records_success_and_failure(monkeypatch):
    from backend.infrastructure.vehicle import mavlink_client

    @contextmanager
    def fake_span(*args, **kwargs):
        yield SimpleNamespace(set_attribute=lambda *a, **k: None)

    monkeypatch.setattr(mavlink_client, "observed_span", fake_span)

    class Factory:
        def command_long_encode(self, *args):
            return {"args": args}

    class Vehicle:
        _master = SimpleNamespace(target_system=1, target_component=1)
        message_factory = Factory()

        def __init__(self):
            self.sent = []

        def send_mavlink(self, msg):
            self.sent.append(msg)

        def flush(self):
            return None

    drone = mavlink_client.MavlinkDrone("udp:127.0.0.1:14550", heartbeat_timeout=1)
    drone.vehicle = Vehicle()
    drone._send_command_long(command=22, p1=1.0)
    assert drone.vehicle.sent

    def fail_send(_msg):
        raise RuntimeError("send failed")

    drone.vehicle.send_mavlink = fail_send
    with pytest.raises(RuntimeError, match="send failed"):
        drone._send_command_long(command=22, p1=1.0)


@pytest.mark.asyncio
async def test_mapping_save_wrapper_records_failure(monkeypatch):
    from backend.modules.warehouse.service import live_map_storage
    from backend.modules.warehouse.service import raw_pointcloud_live_map_bridge as bridge

    async def fail_save_upload(**kwargs):
        raise live_map_storage.LiveMapStorageError("disk full")

    monkeypatch.setattr(
        live_map_storage.warehouse_live_map_chunk_storage,
        "save_upload",
        fail_save_upload,
    )

    xyz = np.asarray([[1.0, 2.0, 3.0]], dtype=np.float32)
    with pytest.raises(live_map_storage.LiveMapStorageError, match="disk full"):
        await bridge._store_and_publish_pointcloud_chunk(
            flight_id="flight-1",
            sequence=1,
            xyz=xyz,
            persist_to_disk=True,
        )


@pytest.mark.asyncio
async def test_video_pipeline_records_latency_and_detection_count(monkeypatch, tmp_path):
    from backend.modules.video_analysis.service import pipeline

    @dataclass
    class FakeJob:
        id: str = "job-1"
        video_id: str = "video-1"
        model_name: str = "fake-yolo.pt"
        confidence_threshold: float = 0.5
        frame_stride_seconds: float = 1.0

    @dataclass
    class FakeVideo:
        id: str = "video-1"
        mission_id: str = "mission-1"
        org_id: int = 1
        storage_path: str = "video.mp4"

    class FakeRepo:
        async def get_job(self, job_id):
            return FakeJob(id=job_id)

        async def get_video(self, video_id):
            return FakeVideo(id=video_id)

        async def mark_job_running(self, job):
            return None

        async def update_video_metadata(self, *args, **kwargs):
            return None

        async def flush_batch(self, *args, **kwargs):
            return None

        async def set_video_status(self, *args, **kwargs):
            return None

        async def mark_job_completed(self, *args, **kwargs):
            return None

        async def mark_job_failed(self, *args, **kwargs):
            return None

    class FakeDetector:
        def __init__(self, *args, **kwargs):
            return None

        def predict(self, image_bgr):
            return [
                SimpleNamespace(
                    label="person",
                    confidence=0.9,
                    x1=0.0,
                    y1=0.0,
                    x2=1.0,
                    y2=1.0,
                    raw={},
                )
            ]

    recorded: list[tuple[str, float]] = []
    monkeypatch.setattr(pipeline, "VideoAnalysisRepository", lambda db: FakeRepo())
    monkeypatch.setattr(pipeline, "YoloFrameDetector", FakeDetector)
    monkeypatch.setattr(
        pipeline,
        "read_video_metadata",
        lambda _path: SimpleNamespace(fps=30.0, width=640, height=480, duration_seconds=1.0),
    )
    monkeypatch.setattr(
        pipeline,
        "iter_frames",
        lambda *a, **k: iter(
            [
                SimpleNamespace(
                    frame_index=1,
                    timestamp_seconds=0.0,
                    image_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
                )
            ]
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "metric_record",
        lambda name, value, attrs=None: recorded.append((name, value)),
    )

    db = SimpleNamespace(rollback=lambda: None)
    analyzer = pipeline.OfflineVideoAnalysisPipeline(db, evidence_root=tmp_path)
    monkeypatch.setattr(analyzer, "_save_crop", lambda **kwargs: Path("crop.jpg"))

    await analyzer.run("job-1")

    assert any(name == "video_inference_latency" for name, _ in recorded)
    assert any(name == "video_detection_count" and value == 1 for name, value in recorded)


def test_correlation_middleware_sets_headers():
    import asyncio

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from backend.observability.correlation import CorrelationMiddleware

    app = FastAPI()
    app.add_middleware(CorrelationMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    async def run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ping")
            assert response.status_code == 200
            assert response.headers.get("X-Request-ID")
            assert response.headers.get("X-Correlation-ID")

    asyncio.run(run())


def test_http_metrics_increment_on_request(monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, Client

    from backend.observability import prometheus_metrics
    from backend.observability.metrics import setup_metrics

    monkeypatch.setenv("PROMETHEUS_METRICS_ENABLED", "true")
    app = FastAPI()
    setup_metrics(app)

    @app.get("/test-route")
    def test_route():
        return {"ok": True}

    before = prometheus_metrics.http_requests_total.labels(
        method="GET", route="/test-route", status_code="200"
    )._value.get()  # noqa: SLF001

    with Client(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = client.get("/test-route")
        assert response.status_code == 200

    after = prometheus_metrics.http_requests_total.labels(
        method="GET", route="/test-route", status_code="200"
    )._value.get()  # noqa: SLF001
    assert after > before


def test_audit_event_emits_structured_fields(caplog):
    from backend.observability.audit import emit_audit_event

    with caplog.at_level("INFO", logger="audit"):
        emit_audit_event(
            event_name="test_event",
            action="create",
            resource_type="mission",
            resource_id="m-1",
            result="success",
            actor_type="user",
            actor_id="42",
            reason="operator update",
            extra={
                "old_value": {"translation": {"x": 0}},
                "new_value": {"translation": {"x": 1}, "access_token": "do-not-log"},
                "covariance": [0.1, 0.2],
            },
        )
    record = next(record for record in caplog.records if "test_event" in record.message)
    assert record.reason == "operator update"
    assert record.old_value == {"translation": {"x": 0}}
    assert record.new_value["access_token"] == "[redacted]"
    assert record.covariance == [0.1, 0.2]


def test_normalize_error_type_maps_db_errors():
    from backend.observability.errors import normalize_error_type
    from sqlalchemy.exc import OperationalError

    assert normalize_error_type(TimeoutError()) == "timeout"
    assert normalize_error_type(OperationalError("stmt", {}, ConnectionError())) == "connection_error"


def test_db_error_increments_metric():
    from backend.observability import prometheus_metrics
    from backend.observability.database import record_db_error

    before = prometheus_metrics.db_errors_total.labels(
        operation="write", error_type="runtime_error"
    )._value.get()  # noqa: SLF001
    record_db_error("write", RuntimeError("disk full"))
    after = prometheus_metrics.db_errors_total.labels(
        operation="write", error_type="runtime_error"
    )._value.get()  # noqa: SLF001
    assert after > before


def test_trace_context_filter_adds_ids():
    import logging

    from backend.observability.context import set_correlation_id, set_request_id
    from backend.observability.logging import TraceContextFilter

    set_request_id("req-1")
    set_correlation_id("corr-1")
    record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
    assert TraceContextFilter().filter(record) is True
    assert record.request_id == "req-1"
    assert record.correlation_id == "corr-1"
