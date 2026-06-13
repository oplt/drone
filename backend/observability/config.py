from __future__ import annotations

import os
from dataclasses import dataclass

from backend.core.config.runtime import settings


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


@dataclass(frozen=True)
class ObservabilityConfig:
    enabled: bool = True
    service_name: str = "drone-api"
    environment: str = "local"
    otlp_endpoint: str = "http://127.0.0.1:4318"
    traces_exporter: str = "otlp"
    metrics_exporter: str = "none"
    prometheus_metrics_enabled: bool = True
    prometheus_metrics_path: str = "/metrics"


def load_config() -> ObservabilityConfig:
    enabled_default = env_bool("OTEL_ENABLED", settings.otel_enabled)
    local_endpoint = env_str("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    configured_endpoint = settings.otel_endpoint or settings.otel_exporter_otlp_endpoint
    endpoint = (
        local_endpoint
        if "OTEL_EXPORTER_OTLP_ENDPOINT" in os.environ
        else configured_endpoint
    )

    return ObservabilityConfig(
        enabled=env_bool("OBSERVABILITY_ENABLED", enabled_default),
        service_name=env_str("OTEL_SERVICE_NAME", settings.otel_service_name or "drone-api"),
        environment=settings.app_env or env_str("APP_ENV", "local"),
        otlp_endpoint=(endpoint or "http://127.0.0.1:4318").rstrip("/"),
        traces_exporter=env_str("OTEL_TRACES_EXPORTER", "otlp").lower(),
        metrics_exporter=env_str("OTEL_METRICS_EXPORTER", "none").lower(),
        prometheus_metrics_enabled=env_bool("PROMETHEUS_METRICS_ENABLED", True),
        prometheus_metrics_path=env_str("PROMETHEUS_METRICS_PATH", "/metrics"),
    )
