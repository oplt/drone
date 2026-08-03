import json
import pytest
from pathlib import Path
from fastapi import HTTPException

from sqlalchemy.orm import attributes

from backend.entrypoints.api.app import app
from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.agriculture.models import AgricultureFlight, _protect_flight_snapshot
from backend.modules.identity.dependencies import OrgUser, require_mission_exec
from backend.modules.identity.models import UserRole


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_agriculture_runtime_commands_require_mission_execution_role():
    viewer = OrgUser(user=type("User", (), {"role": UserRole.viewer})(), org_id=7)
    with pytest.raises(HTTPException) as denied:
        await require_mission_exec(viewer)
    assert denied.value.status_code == 403
    pilot = OrgUser(user=type("User", (), {"role": UserRole.pilot})(), org_id=7)
    assert await require_mission_exec(pilot) is pilot


def test_every_agri_priority_has_release_evidence_and_acceptance_metrics():
    manifest = json.loads(
        (ROOT / "backend/modules/agriculture/readiness.json").read_text(encoding="utf-8")
    )
    assert set(manifest["priorities"]) == {"P0", "P1", "P2", "P3"}
    for priority in manifest["priorities"].values():
        for key in ("contract", "lineage", "worker", "ui", "tests", "acceptance"):
            assert priority[key]
        assert (ROOT / priority["contract"]).is_file()
        assert (ROOT / priority["lineage"]).is_file()
        assert (ROOT / priority["ui"]).is_file()
        assert priority["worker"] in celery_app.tasks
        assert all((ROOT / test).is_file() for test in priority["tests"])


def test_agriculture_release_contract_exposes_required_end_state_routes():
    paths = app.openapi()["paths"]
    required = {
        "/agriculture/flights/{flight_id}/quality",
        "/agriculture/analysis-runs/{run_id}/observations",
        "/agriculture/flights/{flight_id}/compare",
        "/agriculture/comparisons/{comparison_id}/trends",
        "/agriculture/flights/{flight_id}/sensor-status",
        "/agriculture/analysis-runs/{run_id}/prescription-drafts",
        "/agriculture/prescription-drafts/{draft_id}/approval",
        "/agriculture/analysis-runs/{run_id}/exports",
        "/agriculture/analysis-runs/{run_id}/report-snapshots",
        "/agriculture/operations/storage/readiness",
        "/agriculture/operations/storage/restore-drill",
    }
    assert required <= set(paths)


def test_readiness_manifest_keeps_safety_gates_explicit():
    priorities = json.loads(
        (ROOT / "backend/modules/agriculture/readiness.json").read_text(encoding="utf-8")
    )["priorities"]
    assert priorities["P1"]["acceptance"]["calibration_required"] is True
    assert priorities["P2"]["acceptance"]["human_review_required"] is True
    assert priorities["P3"]["acceptance"]["approved_rule_required"] is True
    assert priorities["P3"]["acceptance"]["audit_required"] is True


def test_flight_input_manifest_is_immutable_after_processing_starts():
    flight = AgricultureFlight(
        mission_id="mission-dod",
        field_id=7,
        status="processing",
        profile_snapshot={"crop_type": "wheat", "growth_stage": "tillering"},
        input_manifest={"telemetry_checksum": "original"},
    )
    attributes.instance_state(flight)._commit_all(flight.__dict__)
    flight.input_manifest = {"telemetry_checksum": "changed"}
    try:
        _protect_flight_snapshot(None, None, flight)
    except ValueError as exc:
        assert "input manifests are immutable" in str(exc)
    else:
        raise AssertionError("processed flight input manifest mutation was accepted")
