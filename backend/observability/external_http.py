"""Outbound HTTP client instrumentation for external services."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from backend.observability import prometheus_metrics
from backend.observability.audit import emit_audit_event
from backend.observability.errors import normalize_error_type

logger = logging.getLogger(__name__)


def _endpoint_group(method: str, url: str) -> str:
    try:
        path = httpx.URL(url).path or "/"
    except Exception:
        return "unknown"
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "/"
    if parts[0].isdigit():
        return f"/{{id}}"
    normalized: list[str] = []
    for part in parts[:3]:
        normalized.append(part if part.isalpha() else "{id}")
    return "/" + "/".join(normalized)


class InstrumentedAsyncClient:
    """Thin httpx.AsyncClient wrapper that records metrics and traces."""

    def __init__(self, service_name: str, **kwargs: Any) -> None:
        self.service_name = service_name
        self._client = httpx.AsyncClient(**kwargs)

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        endpoint_group = _endpoint_group(method, url)
        started = time.perf_counter()
        span_cm: Any = None
        try:
            from opentelemetry import trace

            tracer = trace.get_tracer("drone.external_http")
            span_cm = tracer.start_as_current_span(
                f"external.{self.service_name}",
                attributes={
                    "external.service.name": self.service_name,
                    "http.method": method.upper(),
                    "http.route": endpoint_group,
                },
            )
            span_cm.__enter__()
            response = await self._client.request(method, url, **kwargs)
            status = str(response.status_code)
            prometheus_metrics.external_api_requests_total.labels(
                service=self.service_name,
                endpoint_group=endpoint_group,
                status_code=status,
            ).inc()
            if response.status_code >= 400:
                prometheus_metrics.external_api_errors_total.labels(
                    service=self.service_name,
                    error_type=f"http_{response.status_code // 100}xx",
                ).inc()
                emit_audit_event(
                    event_name="external_api_failure",
                    action="request",
                    resource_type="external_api",
                    resource_id=self.service_name,
                    result="failure",
                    error_type=f"http_{response.status_code}",
                    extra={"endpoint_group": endpoint_group},
                )
            return response
        except Exception as exc:
            error_type = normalize_error_type(exc)
            prometheus_metrics.external_api_errors_total.labels(
                service=self.service_name,
                error_type=error_type,
            ).inc()
            emit_audit_event(
                event_name="external_api_failure",
                action="request",
                resource_type="external_api",
                resource_id=self.service_name,
                result="failure",
                error_type=error_type,
                extra={"endpoint_group": endpoint_group},
            )
            raise
        finally:
            elapsed = time.perf_counter() - started
            prometheus_metrics.external_api_request_duration_seconds.labels(
                service=self.service_name,
                endpoint_group=endpoint_group,
            ).observe(elapsed)
            if span_cm is not None:
                try:
                    span_cm.__exit__(None, None, None)
                except Exception:
                    pass

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> InstrumentedAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()
