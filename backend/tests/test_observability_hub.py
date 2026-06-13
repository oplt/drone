from __future__ import annotations

import pytest


def test_observability_links_return_configured_urls(monkeypatch):
    from backend.modules.observability import service

    monkeypatch.setattr(service.settings, "grafana_public_url", "https://grafana.example.com")
    monkeypatch.setattr(service.settings, "prometheus_public_url", "https://prometheus.example.com")
    monkeypatch.setattr(service.settings, "grafana_fleet_dashboard_path", "/d/fleet/fleet-health")
    monkeypatch.setattr(service.settings, "grafana_api_dashboard_path", "/d/api/api-observability")
    monkeypatch.setattr(service.settings, "grafana_workers_dashboard_path", "/d/workers/worker-observability")
    monkeypatch.setattr(service.settings, "grafana_video_dashboard_path", "/d/video/video-pipeline")
    monkeypatch.setattr(service.settings, "grafana_mavlink_dashboard_path", "/d/mavlink/mavlink-telemetry")

    links = service.get_observability_links()

    assert links.grafanaBaseUrl == "https://grafana.example.com"
    assert links.prometheusUrl == "https://prometheus.example.com/graph"
    assert links.fleetDashboardUrl == "https://grafana.example.com/d/fleet/fleet-health"
    assert links.apiDashboardUrl == "https://grafana.example.com/d/api/api-observability"
    assert links.workersDashboardUrl == "https://grafana.example.com/d/workers/worker-observability"
    assert links.videoDashboardUrl == "https://grafana.example.com/d/video/video-pipeline"
    assert links.mavlinkDashboardUrl == "https://grafana.example.com/d/mavlink/mavlink-telemetry"
    assert links.tracesUrl == "https://grafana.example.com/explore"


def test_prometheus_graph_url_is_not_duplicated(monkeypatch):
    from backend.modules.observability import service

    monkeypatch.setattr(service.settings, "grafana_public_url", "")
    monkeypatch.setattr(service.settings, "prometheus_public_url", "https://prometheus.example.com/graph")

    links = service.get_observability_links()

    assert links.prometheusUrl == "https://prometheus.example.com/graph"


@pytest.mark.asyncio
async def test_observability_status_degrades_without_crashing(monkeypatch):
    from backend.modules.observability import service

    monkeypatch.setattr(service.settings, "grafana_public_url", "")
    monkeypatch.setattr(service.settings, "prometheus_public_url", "")

    status = await service.get_observability_status()

    assert status.api.status == "healthy"
    assert status.grafana.status == "unknown"
    assert status.prometheus.status == "unknown"
