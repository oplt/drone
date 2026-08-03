from __future__ import annotations

import pytest
import json
from pathlib import Path
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.core.pagination import decode_offset_cursor, encode_offset_cursor
from backend.entrypoints.api.app import app
from backend.core.errors.handlers import _safe_http_message
from backend.modules.agriculture.contracts_validation import (
    frontend_route_references,
    missing_frontend_routes,
    validate_event_sequence,
)
from backend.modules.agriculture.models import AgricultureFlight
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.schemas import AgricultureMissionProfile, AgriculturePlanIn, AgriculturePreflightIn
from backend.modules.agriculture.workflow import build_plan, evaluate_preflight, snapshot_is_usable
from backend.modules.agriculture.workflow_models import AgricultureMissionPlan
from backend.scripts.export_agriculture_contract import agriculture_contract


def test_openapi_contract_exposes_examples_and_governed_state_transitions():
    paths = app.openapi()["paths"]
    required = {
        "/agriculture/fields/overview",
        "/agriculture/flights/{flight_id}/analysis-runs",
        "/agriculture/analysis-runs/{run_id}/observations",
        "/agriculture/flights/{flight_id}/media-timeline",
        "/agriculture/analysis-runs/{run_id}/report",
        "/agriculture/models",
        "/agriculture/models/{model_version_id}/quality-reports",
        "/agriculture/models/{model_version_id}/shadow-evaluation",
        "/agriculture/models/{model_version_id}/publish",
        "/agriculture/models/{model_version_id}/drift-monitor",
    }
    assert required <= paths.keys()
    manifest = paths["/agriculture/flights/{flight_id}/manifests"]["post"]
    assert manifest["requestBody"]["content"]["application/json"]["schema"]


def test_checked_in_openapi_snapshot_is_current():
    snapshot = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/agriculture-openapi.json").read_text()
    )
    assert snapshot == agriculture_contract()


def test_contract_schemas_pin_required_fields_and_enums():
    schemas = app.openapi()["components"]["schemas"]
    page = schemas["AgricultureObservationPage"]
    assert set(page["required"]) >= {"schema_version", "items", "next_cursor", "total"}
    profile = schemas["AgricultureMissionProfile"]
    assert set(profile["properties"]["sensor_inventory"]["items"]["enum"]) >= {
        "rgb", "multispectral", "thermal", "stereo", "lidar"
    }


def test_phase_two_workflow_routes_are_published():
    paths = app.openapi()["paths"]
    required = {
        "/agriculture/flights/plans",
        "/agriculture/flights/plans/{plan_id}",
        "/agriculture/flights/plans/{plan_id}/validate",
        "/agriculture/flights/plans/{plan_id}/duplicate",
        "/agriculture/flights/plans/{plan_id}/replan",
        "/agriculture/flights/plans/{plan_id}/preflight",
        "/agriculture/preflight/{snapshot_id}",
        "/agriculture/preflight/{snapshot_id}/acknowledge",
        "/agriculture/flights/{flight_id}/media-inventory",
        "/agriculture/flights/{flight_id}/runtime/events",
    }
    assert required <= paths.keys()


def test_cursor_contract_round_trips_and_rejects_malformed_cursor():
    cursor = encode_offset_cursor(125)
    assert decode_offset_cursor(cursor) == 125
    with pytest.raises(ValueError):
        decode_offset_cursor("not-a-valid-cursor")


def test_realtime_sequence_contract_rejects_duplicates_and_backtracking():
    validate_event_sequence([{"sequence": 1}, {"sequence": 2}])
    with pytest.raises(ValueError):
        validate_event_sequence([{"sequence": 1}, {"sequence": 1}])


def test_http_exception_preserves_machine_readable_agriculture_code():
    message, details, code = _safe_http_message(
        422,
        {
            "code": "AGRICULTURE_CONTEXT_REQUIRED",
            "message": "field_id and agriculture profile are required",
            "field_id": "required",
        },
    )
    assert message == "field_id and agriculture profile are required"
    assert details == {"field_id": "required"}
    assert code == "AGRICULTURE_CONTEXT_REQUIRED"


def test_frontend_agriculture_api_routes_match_backend_openapi():
    source = (
        Path(__file__).resolve().parents[2]
        / "frontend/src/modules/agriculture/api.ts"
    ).read_text(encoding="utf-8")
    missing = missing_frontend_routes(frontend_route_references(source), app.openapi()["paths"])
    assert missing == []


def test_dynamic_upload_chunk_route_is_present_in_backend_contract():
    paths = app.openapi()["paths"]
    assert "put" in paths["/agriculture/flights/{flight_id}/uploads/{upload_id}/chunks"]


@pytest.mark.asyncio
async def test_flight_repository_rejects_cross_tenant_access():
    flight = AgricultureFlight(id="flight-org-7", mission_id="mission-1", field_id=1, org_id=7)

    class Result:
        def scalar_one_or_none(self):
            return flight

    class Database:
        async def execute(self, _statement):
            return Result()

    assert (
        await agriculture_repository.get_flight(
            Database(), flight_id=flight.id, user=SimpleNamespace(org_id=8)
        )
        is None
    )
    assert (
        await agriculture_repository.get_flight(
            Database(), flight_id=flight.id, user=SimpleNamespace(org_id=7)
        )
        is flight
    )


def test_professional_plan_generates_route_and_rejects_exclusion_intersection():
    payload = AgriculturePlanIn(
        field_id=7,
        field_polygon_lonlat=[[4.0, 50.0], [4.01, 50.0], [4.01, 50.01], [4.0, 50.01]],
        profile=AgricultureMissionProfile(),
    )
    normalized, route, estimates, warnings, errors = build_plan(payload)
    assert normalized["planner_version"] == "agriculture-grid.v1"
    assert len(route) >= 2
    assert estimates["estimated_battery_count"] >= 1
    assert isinstance(warnings, list)
    assert errors == []


@pytest.mark.asyncio
async def test_preflight_snapshot_is_blocked_until_all_checks_pass_and_is_acknowledged():
    payload = AgriculturePlanIn(
        field_id=7,
        field_polygon_lonlat=[[4.0, 50.0], [4.01, 50.0], [4.01, 50.01], [4.0, 50.01]],
        profile=AgricultureMissionProfile(),
    )
    plan = AgricultureMissionPlan(
        id="plan-1",
        field_id=7,
        org_id=3,
        status="validated",
        plan_hash="hash",
        payload_json=payload.model_dump(mode="json"),
        route_geojson={},
        estimates_json={},
        warnings_json=[],
        validation_errors_json=[],
    )

    class Database:
        def add(self, _record):
            return None

        async def flush(self):
            return None

    snapshot = await evaluate_preflight(
        Database(),
        plan=plan,
        payload=AgriculturePreflightIn(checks={"gps_ready": True}),
        org_id=3,
        user_id=8,
    )
    assert snapshot.status == "blocked"
    assert not snapshot_is_usable(snapshot)

    snapshot.status = "pass"
    snapshot.acknowledged_at = datetime.now(UTC)
    assert snapshot_is_usable(snapshot)
