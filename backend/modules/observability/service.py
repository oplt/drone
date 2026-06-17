from __future__ import annotations

import asyncio
import time
from urllib.parse import urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import RuntimeSettings, settings
from backend.modules.fleet.models import DeviceReadiness
from backend.modules.missions.runtime_models import MissionRuntime
from backend.modules.observability.schemas import (
    ContextOption,
    ObservabilityContextOptions,
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
    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
        return await _probe_health(client, url)


async def _probe_health(client: httpx.AsyncClient, url: str | None) -> str:
    if not url:
        return "unknown"
    try:
        response = await client.get(url)
        if response.status_code < 500:
            return "healthy"
        return "degraded"
    except httpx.TimeoutException:
        return "degraded"
    except httpx.HTTPError:
        return "unknown"


def _mission_label(name: str | None, client_flight_id: str) -> str:
    clean_name = (name or "").strip()
    short_id = client_flight_id[:8]
    if clean_name:
        return f"{clean_name} ({short_id})"
    return client_flight_id


async def get_observability_context_options(
    db: AsyncSession,
    *,
    org_id: int | None,
    user_id: int | None = None,
    limit: int = 100,
) -> ObservabilityContextOptions:
    """Build the drone/mission selection lists from the database.

    The returned ``value`` for each option is the identifier that the
    telemetry pipeline actually emits as a metric/trace label, so selecting
    an option produces Grafana links that match real data:

    * missions → ``mission_runtimes.client_flight_id`` (label ``mission.id``)
    * drones   → ``device_readiness.device_id`` (label ``drone.id``)
    """
    safe_limit = max(1, min(int(limit or 100), 500))

    mission_stmt = select(
        MissionRuntime.client_flight_id, MissionRuntime.mission_name
    )
    if org_id is not None:
        mission_stmt = mission_stmt.where(MissionRuntime.org_id == org_id)
    elif user_id is not None:
        mission_stmt = mission_stmt.where(MissionRuntime.user_id == user_id)
    mission_stmt = mission_stmt.order_by(MissionRuntime.created_at.desc()).limit(safe_limit)

    mission_rows = (await db.execute(mission_stmt)).all()
    missions = [
        ContextOption(value=client_flight_id, label=_mission_label(name, client_flight_id))
        for client_flight_id, name in mission_rows
        if client_flight_id
    ]

    device_stmt = select(DeviceReadiness.device_id, DeviceReadiness.device_name)
    if org_id is not None:
        device_stmt = device_stmt.where(DeviceReadiness.org_id == org_id)
    device_stmt = device_stmt.order_by(DeviceReadiness.device_name.asc()).limit(safe_limit)

    device_rows = (await db.execute(device_stmt)).all()
    seen: set[str] = set()
    drones: list[ContextOption] = []
    for device_id, device_name in device_rows:
        if not device_id or device_id in seen:
            continue
        seen.add(device_id)
        clean_name = (device_name or "").strip()
        label = f"{clean_name} ({device_id})" if clean_name else device_id
        drones.append(ContextOption(value=device_id, label=label))

    return ObservabilityContextOptions(drones=drones, missions=missions)


# Cache the health probe for the poll window so the 30s frontend poll doesn't
# trigger a fresh fan-out of external HTTP (with redirect chains) every time,
# and concurrent callers coalesce onto one probe.
_status_lock = asyncio.Lock()
_status_cache: ObservabilityStatus | None = None
_status_cache_at: float = 0.0


async def get_observability_status(config: RuntimeSettings = settings) -> ObservabilityStatus:
    global _status_cache, _status_cache_at

    ttl = max(0.0, float(getattr(config, "observability_status_cache_ttl_s", 25.0)))

    def _fresh_cache() -> ObservabilityStatus | None:
        if ttl <= 0.0 or _status_cache is None:
            return None
        if (time.monotonic() - _status_cache_at) < ttl:
            return _status_cache
        return None

    cached = _fresh_cache()
    if cached is not None:
        return cached

    async with _status_lock:
        # Re-check after acquiring so concurrent callers share one probe.
        cached = _fresh_cache()
        if cached is not None:
            return cached

        links = get_observability_links(config)
        timeout_s = max(0.25, config.observability_health_timeout_s)

        # Probe cheap health endpoints instead of the dashboard roots so we do
        # not chase /login (grafana) or 301/302 (prometheus) redirect chains.
        grafana_probe = (
            _join_public_url(_clean_url(config.grafana_public_url), "/api/health")
            or links.grafanaBaseUrl
        )
        prometheus_probe = (
            _join_public_url(_clean_url(config.prometheus_public_url), "/-/ready")
            or links.prometheusUrl
        )

        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=False) as client:
            grafana_status, prometheus_status = await asyncio.gather(
                _probe_health(client, grafana_probe),
                _probe_health(client, prometheus_probe),
            )

        status = ObservabilityStatus(
            api=ServiceStatus(status="healthy"),
            prometheus=ServiceStatus(status=prometheus_status, url=links.prometheusUrl),
            grafana=ServiceStatus(status=grafana_status, url=links.grafanaBaseUrl),
            tempo=ServiceStatus(status="unknown", url=links.tracesUrl),
            telemetry=TelemetryStatus(status="unknown", lagSeconds=None),
            workers=WorkerStatus(status="unknown", queueDepth=None),
        )
        _status_cache = status
        _status_cache_at = time.monotonic()
        return status
