"""Unit tests for PROD-002 flight comparability scoring."""

from types import SimpleNamespace

from backend.modules.agriculture.comparability import score_comparability
from backend.modules.agriculture.report_service import build_decision_report_snapshot


def _flight(**overrides):
    base = dict(
        id="flight-a",
        field_id=1,
        season="2026",
        profile_snapshot={"crop_type": "maize", "growth_stage": "V6", "sensor_inventory": ["rgb"]},
        quality_summary={"status": "pass", "score": 0.9},
        input_manifest={},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _run(**overrides):
    base = dict(
        id="run-a",
        model_versions={"detector": "v1"},
        calibration_versions={"rgb": "cal-1"},
        quality_gate={"status": "pass"},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_comparability_eligible_when_inputs_match():
    result = score_comparability(
        current=_flight(),
        reference=_flight(id="flight-b"),
        current_run=_run(),
        reference_run=_run(id="run-b"),
        alignment={"status": "aligned", "alignment_score": 0.8},
    )
    assert result["eligible"] is True
    assert result["status"] == "eligible"
    assert result["score"] >= 0.45
    assert not result["blockers"]


def test_model_mismatch_blocks_silent_deltas():
    result = score_comparability(
        current=_flight(),
        reference=_flight(id="flight-b"),
        current_run=_run(model_versions={"detector": "v1"}),
        reference_run=_run(id="run-b", model_versions={"detector": "v2"}),
        alignment={"status": "aligned", "alignment_score": 0.9},
    )
    assert result["eligible"] is False
    assert "model_release_mismatch" in result["blockers"]
    assert "model_versions_changed" in result["warnings"]


def test_sensor_mismatch_is_a_blocker():
    result = score_comparability(
        current=_flight(),
        reference=_flight(id="flight-b", profile_snapshot={"crop_type": "maize", "growth_stage": "V6", "sensor_inventory": ["multispectral"]}),
        current_run=_run(),
        reference_run=_run(id="run-b"),
        alignment={"status": "aligned", "alignment_score": 0.9},
    )
    assert "sensor_inventory_mismatch" in result["blockers"]
    assert result["eligible"] is False


def test_decision_report_includes_comparable_inputs_and_actions():
    snapshot, checksum = build_decision_report_snapshot(
        field=SimpleNamespace(id=7, name="North"),
        current_flight=_flight(),
        reference_flight=_flight(id="flight-b"),
        current_run=_run(id="run-a"),
        reference_run=_run(id="run-b"),
        comparability={"score": 0.8, "status": "eligible", "policy_version": "flight_comparability_v1", "warnings": [], "blockers": []},
        changes=[
            SimpleNamespace(
                id="chg-1",
                observation_type="weed_detection",
                state="new",
                confidence=0.7,
                evidence_ids=["e1"],
                geometry_geojson={"type": "Point", "coordinates": [1, 2]},
                current_observation_id="obs-1",
                previous_observation_id=None,
                delta_intensity=0.2,
                uncertainty={},
            )
        ],
        reviewed_observations=[
            SimpleNamespace(
                id="obs-1",
                review_state="confirmed",
                observation_type="weed_detection",
                evidence_ids=["e1"],
                model_version="v1",
                confidence=0.7,
                severity=0.8,
            )
        ],
        approved_actions=[
            SimpleNamespace(
                id="act-1",
                issue_type="weed_detection",
                priority_rank=1,
                status="approved",
                severity=0.8,
                confidence=0.7,
                source_ids=["obs-1"],
                waypoint_geojson={"type": "Point", "coordinates": [1, 2]},
            )
        ],
    )
    assert checksum
    assert snapshot["template_key"] == "decision"
    assert snapshot["comparable_inputs"]["current_flight_id"] == "flight-a"
    assert snapshot["approved_actions"][0]["id"] == "act-1"
    assert snapshot["reviewed_evidence"][0]["observation_id"] == "obs-1"
    assert snapshot["features"][0]["properties"]["id"] == "chg-1"
