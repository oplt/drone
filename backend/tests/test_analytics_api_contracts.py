from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.modules.analytics.api import router
from backend.modules.analytics.api.analytics_route_deps import VALID_TELEMETRY_SUMMARY_RESOLUTIONS
from backend.modules.analytics.api.analytics_route_schemas import AnalyticsOverviewResponse
from backend.modules.analytics.overview_helpers import daterange, date_key, haversine_km


def test_analytics_router_keeps_public_prefixes_and_paths() -> None:
    assert router.prefix == "/analytics"
    paths = {route.path for route in router.routes}
    assert "/analytics/overview" in paths
    assert "/analytics/flights/{flight_id}/telemetry/summary" in paths


def test_valid_telemetry_summary_resolutions_are_fixed() -> None:
    assert VALID_TELEMETRY_SUMMARY_RESOLUTIONS == {1, 10, 60}


def test_analytics_overview_response_requires_all_sections() -> None:
    payload = AnalyticsOverviewResponse.model_validate(
        {
            "summary": {
                "active_flights": 0,
                "flights_24h": 0,
                "telemetry_24h": 0,
                "flight_hours_7d": 0.0,
                "avg_battery_24h": None,
            },
            "trends": {
                "days": ["2026-08-14"],
                "flight_hours": [0.0],
                "flight_counts": [0],
                "telemetry_counts": [0],
            },
            "coverage": [],
            "recent_flights": [],
            "events": [],
            "system": {
                "telemetry_running": False,
                "active_connections": 0,
                "last_update": None,
                "mavlink_connected": False,
            },
        }
    )
    assert payload.summary.active_flights == 0
    assert payload.trends.days == ["2026-08-14"]


def test_daterange_builds_ascending_day_keys() -> None:
    end = datetime(2026, 8, 14, tzinfo=UTC)
    days = daterange(end, 3)
    assert [date_key(day) for day in days] == ["2026-08-12", "2026-08-13", "2026-08-14"]


def test_haversine_km_is_zero_for_identical_points() -> None:
    assert haversine_km(47.0, 8.0, 47.0, 8.0) == pytest.approx(0.0)
