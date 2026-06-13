from __future__ import annotations

from pydantic import BaseModel


class ObservabilityLinks(BaseModel):
    grafanaBaseUrl: str | None = None
    prometheusUrl: str | None = None
    fleetDashboardUrl: str | None = None
    apiDashboardUrl: str | None = None
    workersDashboardUrl: str | None = None
    videoDashboardUrl: str | None = None
    mavlinkDashboardUrl: str | None = None
    tracesUrl: str | None = None


class ServiceStatus(BaseModel):
    status: str
    url: str | None = None


class TelemetryStatus(BaseModel):
    status: str
    lagSeconds: float | None = None


class WorkerStatus(BaseModel):
    status: str
    queueDepth: int | None = None


class ObservabilityStatus(BaseModel):
    api: ServiceStatus
    prometheus: ServiceStatus
    grafana: ServiceStatus
    tempo: ServiceStatus
    telemetry: TelemetryStatus
    workers: WorkerStatus
