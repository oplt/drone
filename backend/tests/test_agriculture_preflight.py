from types import SimpleNamespace

import pytest

from backend.modules.agriculture.preflight_service import _report_status, _status, evaluate_server_preflight
from backend.modules.agriculture.workflow_models import AgricultureMissionPlan


def test_server_status_is_fail_closed_and_report_skip_blocks():
    assert _status([{"status": "PASS"}, {"status": "WARN"}]) == "warning"
    assert _status([{"status": "PASS"}, {"status": "BLOCK"}]) == "blocked"
    report = SimpleNamespace(base_checks=[SimpleNamespace(name="GPS Fix Type", status="SKIP", message="no fix")], mission_checks=[])
    assert _report_status(report, {"GPS Fix Type"})[0] == "BLOCK"


@pytest.mark.asyncio
async def test_server_preflight_ignores_client_booleans_and_exposes_provider_sources(monkeypatch):
    plan = AgricultureMissionPlan(
        id="pf-plan", field_id=7, org_id=3, status="validated", plan_hash="hash", grid_revision=1,
        payload_json={"field_polygon_lonlat": [[4.0, 50.0], [4.01, 50.0], [4.01, 50.01], [4.0, 50.01]], "profile": {"requested_analyses": [], "sensor_inventory": ["rgb"]}},
        route_geojson={"type": "LineString", "coordinates": [[4.001, 50.001], [4.002, 50.002]]}, estimates_json={}, warnings_json=[], validation_errors_json=[],
    )

    async def runtime(_plan):
        return [
            {"code": "gps_ready", "label": "GPS", "status": "PASS", "blocking": False, "message": "fresh", "source": "runtime"},
            {"code": "battery_ready", "label": "Battery", "status": "PASS", "blocking": False, "message": "fresh", "source": "runtime"},
            {"code": "weather_safe", "label": "Weather", "status": "PASS", "blocking": False, "message": "safe", "source": "weather"},
        ], SimpleNamespace(video=object()), object()

    class Database:
        def add(self, _value):
            return None

        async def flush(self):
            return None

        async def scalars(self, _query):
            return SimpleNamespace(all=lambda: [])

        async def execute(self, _query):
            return SimpleNamespace(all=lambda: [])

    monkeypatch.setattr("backend.modules.agriculture.preflight_service._runtime_checks", runtime)
    snapshot = await evaluate_server_preflight(Database(), plan=plan, user=SimpleNamespace(org_id=3, user=SimpleNamespace(id=9)))
    assert snapshot.status == "blocked"  # permission provider is unavailable, despite any client checkbox
    assert {check["code"] for check in snapshot.checks_json} == {"field_boundary", "route_coverage", "drone_connected", "gps_ready", "battery_ready", "camera_ready", "storage_ready", "weather_safe", "permissions_granted", "model_ready", "calibration_ready"}
    assert all(check["source"] for check in snapshot.checks_json)
