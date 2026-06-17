from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import unquote

from backend.core.config.runtime import settings
from backend.observability.config import load_config

logger = logging.getLogger(__name__)

_configured = False
_libraries_instrumented = False
_SIGNALS = {"traces", "metrics", "logs"}


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _env_optional(name: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else ""


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _otlp_headers() -> dict[str, str] | None:
    raw = _env_optional("OTEL_EXPORTER_OTLP_HEADERS")
    if not raw and "OTEL_EXPORTER_OTLP_ENDPOINT" not in os.environ:
        raw = settings.otel_exporter_otlp_headers
    if raw == "Authorization=Basic%20<base64-instance-id-colon-token>":
        raw = ""
    if not raw:
        return None
    headers: dict[str, str] = {}
    for item in raw.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = unquote(value.strip())
        if key and value:
            headers[key] = value
    return headers or None


def _resource_attributes() -> dict[str, str]:
    raw = settings.otel_resource_attributes or _env_optional("OTEL_RESOURCE_ATTRIBUTES")
    attrs: dict[str, str] = {}
    for item in raw.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            attrs[key] = value
    return attrs


def _base_endpoint() -> str:
    return load_config().otlp_endpoint


def _signal_endpoint(signal: str, base_endpoint: str) -> str:
    specific_settings = {
        "traces": settings.otel_exporter_otlp_traces_endpoint,
        "metrics": settings.otel_exporter_otlp_metrics_endpoint,
        "logs": settings.otel_exporter_otlp_logs_endpoint,
    }
    specific_env = {
        "traces": "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "metrics": "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "logs": "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
    }
    specific = specific_settings[signal] or _env_optional(specific_env[signal])
    if specific:
        return specific.rstrip("/")

    parts = base_endpoint.split("/")
    if len(parts) >= 2 and parts[-2] == "v1" and parts[-1] in _SIGNALS:
        return "/".join([*parts[:-1], signal])
    return f"{base_endpoint}/v1/{signal}"


def _resource(service_name: str):
    from opentelemetry.sdk.resources import Resource

    attrs = {
        **_resource_attributes(),
        "service.name": service_name,
        "deployment.environment": (
            os.getenv("OTEL_ENVIRONMENT")
            or settings.app_env
            or _env("APP_ENV", "local")
        ),
        "drone.app": "drone-api",
        "drone.autopilot": _env("DRONE_AUTOPILOT", "ardupilot"),
        "drone.simulator": _env("DRONE_SIMULATOR", "gazebo"),
    }
    attrs.setdefault("service.namespace", "drone")

    return Resource.create(
        {
            key: value
            for key, value in attrs.items()
            if isinstance(value, str | bool | int | float)
        }
    )


def setup_observability(app: Any | None = None, *, service_name: str | None = None) -> None:
    """Configure OTLP/HTTP traces, metrics, logs, and app instrumentation.

    Export failures are handled by OpenTelemetry batch processors and must not affect
    control, mapping, or video code paths.
    """

    global _configured
    if _configured:
        if app is not None:
            _instrument_app(app)
        return

    config = load_config()
    if not config.enabled:
        logger.info("Observability disabled by OBSERVABILITY_ENABLED")
        return
    if config.traces_exporter in {"none", "false", "0", "off"}:
        logger.info("OpenTelemetry traces disabled by OTEL_TRACES_EXPORTER")
        return

    resolved_service_name = service_name or config.service_name
    endpoint = config.otlp_endpoint
    headers = _otlp_headers()

    try:
        resource = _resource(resolved_service_name)
        _setup_traces(_signal_endpoint("traces", endpoint), resource, headers)
        if config.metrics_exporter == "otlp":
            _setup_metrics(_signal_endpoint("metrics", endpoint), resource, headers)
        _setup_library_instrumentation()
        if app is not None:
            _instrument_app(app)
        _configured = True
        logger.info(
            "OpenTelemetry configured endpoint=%s service=%s",
            endpoint,
            resolved_service_name,
        )
    except ImportError as exc:
        logger.warning("OpenTelemetry packages unavailable; telemetry disabled: %s", exc)
    except Exception as exc:
        logger.warning("OpenTelemetry setup failed; app continues without OTLP export: %s", exc)


def _setup_traces(endpoint: str, resource: Any, headers: dict[str, str] | None) -> None:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, headers=headers))
    )
    trace.set_tracer_provider(provider)


def _setup_metrics(endpoint: str, resource: Any, headers: dict[str, str] | None) -> None:
    from opentelemetry import metrics
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, headers=headers),
        export_interval_millis=int(
            _env(
                "OTEL_METRIC_EXPORT_INTERVAL_MS",
                str(settings.otel_metric_export_interval_ms),
            )
        ),
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))


def _setup_logs(endpoint: str, resource: Any, headers: dict[str, str] | None) -> None:
    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    except ImportError:
        logger.warning("OpenTelemetry log exporter unavailable; traces/metrics still enabled")
        return

    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, headers=headers))
    )
    set_logger_provider(provider)
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=provider)
    root = logging.getLogger()
    if not any(isinstance(existing, LoggingHandler) for existing in root.handlers):
        root.addHandler(handler)
    logger.info("OpenTelemetry log export configured endpoint=%s", endpoint)


def _setup_library_instrumentation() -> None:
    global _libraries_instrumented
    if _libraries_instrumented:
        return
    try:
        from opentelemetry.instrumentation.logging import LoggingInstrumentor

        LoggingInstrumentor().instrument(set_logging_format=False, log_hook=_log_hook)
    except Exception as exc:
        logger.debug("OpenTelemetry logging correlation skipped: %s", exc)
    try:
        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        RequestsInstrumentor().instrument()
    except Exception as exc:
        logger.debug("OpenTelemetry requests instrumentation skipped: %s", exc)
    _libraries_instrumented = True


def _instrument_app(app: Any) -> None:
    if getattr(app.state, "otel_instrumented", False):
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        app.state.otel_instrumented = True
    except Exception as exc:
        logger.debug("FastAPI OpenTelemetry instrumentation skipped: %s", exc)


def _log_hook(span: Any, record: logging.LogRecord) -> None:
    if span is None:
        return
    context = span.get_span_context()
    if not context.is_valid:
        return
    record.otel_trace_id = format(context.trace_id, "032x")
    record.otel_span_id = format(context.span_id, "016x")
