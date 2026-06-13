from __future__ import annotations

from urllib.parse import urljoin

import httpx

from backend.core.config.runtime import RuntimeSettings, settings
from backend.modules.observability.schemas import (
    ObservabilityLinks,
    ObservabilityStatus,
    ServiceStatus,
    TelemetryStatus,
    WorkerStatus,
)


def _clean_url(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def _join_public_url(base_url: str | None, path: str | None) -> str | None:
    base = _clean_url(base_url)
    if not base:
        return None
    clean_path = (path or "").strip()
    if not clean_path:
        return base
    return urljoin(f"{base.rstrip('/')}/", clean_path.lstrip("/"))


def _prometheus_graph_url(base_url: str | None) -> str | None:
    base = _clean_url(base_url)
    if not base:
        return None
    if base.rstrip("/").endswith("/graph"):
        return base
    return _join_public_url(base, "/graph")


def get_observability_links(config: RuntimeSettings = settings) -> ObservabilityLinks:
    grafana_base = _clean_url(config.grafana_public_url)
    return ObservabilityLinks(
        grafanaBaseUrl=grafana_base,
        prometheusUrl=_prometheus_graph_url(config.prometheus_public_url),
        fleetDashboardUrl=_join_public_url(grafana_base, config.grafana_fleet_dashboard_path),
        apiDashboardUrl=_join_public_url(grafana_base, config.grafana_api_dashboard_path),
        workersDashboardUrl=_join_public_url(grafana_base, config.grafana_workers_dashboard_path),
        videoDashboardUrl=_join_public_url(grafana_base, config.grafana_video_dashboard_path),
        mavlinkDashboardUrl=_join_public_url(grafana_base, config.grafana_mavlink_dashboard_path),
        tracesUrl=_join_public_url(grafana_base, "/explore") if grafana_base else None,
    )


async def _check_url(url: str | None, *, timeout_s: float) -> str:
    if not url:
        return "unknown"
    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            response = await client.get(url)
        if response.status_code < 500:
            return "healthy"
        return "degraded"
    except httpx.TimeoutException:
        return "degraded"
    except httpx.HTTPError:
        return "unknown"


async def get_observability_status(config: RuntimeSettings = settings) -> ObservabilityStatus:
    links = get_observability_links(config)
    timeout_s = max(0.25, config.observability_health_timeout_s)
    grafana_status = await _check_url(links.grafanaBaseUrl, timeout_s=timeout_s)
    prometheus_status = await _check_url(links.prometheusUrl, timeout_s=timeout_s)

    return ObservabilityStatus(
        api=ServiceStatus(status="healthy"),
        prometheus=ServiceStatus(status=prometheus_status, url=links.prometheusUrl),
        grafana=ServiceStatus(status=grafana_status, url=links.grafanaBaseUrl),
        tempo=ServiceStatus(status="unknown", url=links.tracesUrl),
        telemetry=TelemetryStatus(status="unknown", lagSeconds=None),
        workers=WorkerStatus(status="unknown", queueDepth=None),
    )
