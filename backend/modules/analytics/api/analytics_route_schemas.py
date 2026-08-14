from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AnalyticsSummary(BaseModel):
    active_flights: int
    flights_24h: int
    telemetry_24h: int
    flight_hours_7d: float
    avg_battery_24h: float | None


class AnalyticsTrends(BaseModel):
    days: list[str]
    flight_hours: list[float]
    flight_counts: list[int]
    telemetry_counts: list[int]


class AnalyticsCoveragePoint(BaseModel):
    label: str
    value: float


class AnalyticsRecentFlight(BaseModel):
    id: int
    name: str
    status: str
    started_at: str
    ended_at: str | None
    duration_min: float
    distance_km: float
    telemetry_points: int


class AnalyticsEvent(BaseModel):
    id: int
    flight_id: int
    type: str
    created_at: str
    data: dict[str, Any]


class AnalyticsSystem(BaseModel):
    telemetry_running: bool
    active_connections: int
    last_update: Any = None
    mavlink_connected: bool


class AnalyticsOverviewResponse(BaseModel):
    summary: AnalyticsSummary
    trends: AnalyticsTrends
    coverage: list[AnalyticsCoveragePoint]
    recent_flights: list[AnalyticsRecentFlight]
    events: list[AnalyticsEvent]
    system: AnalyticsSystem
