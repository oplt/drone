from types import SimpleNamespace
import pytest

from backend.modules.agriculture.temporal import alignment_metrics, build_changes, summarize_changes
from backend.modules.agriculture.evaluation import drift_report, evaluate_predictions
from backend.modules.agriculture.schemas import AgricultureGridUpdateIn
from backend.modules.agriculture.workflow import update_plan_grid
from backend.modules.agriculture.workflow_models import AgricultureMissionPlan


def _observation(identifier, observation_type="weed", geometry=None, area=10.0, severity=0.5, confidence=0.9, review_state="unreviewed"):
    return SimpleNamespace(id=identifier, observation_type=observation_type, geometry_geojson=geometry or {"type": "Polygon", "coordinates": [[[4.0, 50.0], [4.001, 50.0], [4.001, 50.001], [4.0, 50.0]]]}, area_m2=area, severity=severity, confidence=confidence, review_state=review_state, evidence_ids=[identifier])


def test_temporal_comparison_emits_states_and_keeps_rejected_out():
    current = [_observation("current", area=15, severity=.8), _observation("new", geometry={"type": "Point", "coordinates": [4.1, 50.1]}, area=2)]
    previous = [_observation("previous", area=10, severity=.5), _observation("rejected", review_state="rejected")]
    changes = build_changes(current, previous, current_flight_id="f2", reference_flight_id="f1", field_id=1)
    assert {row["state"] for row in changes} >= {"expanding", "new"}
    assert all("rejected" not in row["evidence_ids"] for row in changes)
    summary = summarize_changes(changes)
    assert summary["new"] == 1
    assert summary["persistent"] == 1
    assert summary["count_change"] == 1
    assert summary["area_change_m2"] == pytest.approx(7)


def test_temporal_comparison_emits_resolved_for_unmatched_previous():
    previous = [_observation("previous")]
    changes = build_changes([], previous, current_flight_id="f2", reference_flight_id="f1", field_id=1)
    assert changes[0]["state"] == "resolved"
    assert changes[0]["current_observation_id"] is None


def test_temporal_comparison_does_not_consume_barely_overlapping_reference():
    current = _observation(
        "current",
        geometry={
            "type": "Polygon",
            "coordinates": [[[0.99, 0.99], [2, 0.99], [2, 2], [0.99, 0.99]]],
        },
    )
    previous = _observation(
        "previous",
        geometry={
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
        },
    )
    changes = build_changes(
        [current],
        [previous],
        current_flight_id="f2",
        reference_flight_id="f1",
        field_id=1,
    )
    assert [row["state"] for row in changes] == ["new", "resolved"]
    assert changes[0]["previous_observation_id"] is None


def test_alignment_is_deterministic_and_reports_failure_reason():
    layer = SimpleNamespace(geojson={"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[4, 50], [4.001, 50], [4.001, 50.001], [4, 50]]]}}]})
    assert alignment_metrics(layer, layer)["status"] == "aligned"
    assert alignment_metrics(None, layer)["failure_reasons"] == ["missing_quality_footprints"]


def test_model_evaluation_reports_quality_and_drift():
    report = evaluate_predictions([{"label": "weed", "x1": 0, "y1": 0, "x2": 10, "y2": 10, "confidence": .8}], [{"label": "weed", "x1": 0, "y1": 0, "x2": 10, "y2": 10}])
    assert report["precision"] == 1 and report["recall"] == 1 and "calibration_mae" in report
    assert drift_report({"canopy": .9}, {"canopy": .5})["status"] == "warning"


def test_grid_revision_rejects_outside_route_and_accepts_inside_route():
    plan = AgricultureMissionPlan(
        id="grid-plan", field_id=7, org_id=3, grid_revision=1, planner_version="agriculture-grid.v1",
        plan_hash="old", status="validated",
        payload_json={"field_polygon_lonlat": [[4.0, 50.0], [4.01, 50.0], [4.01, 50.01], [4.0, 50.01]], "exclusion_zones": [], "obstacle_zones": []},
        route_geojson={"type": "LineString", "coordinates": [[4.001, 50.001], [4.002, 50.002]]}, estimates_json={}, warnings_json=[], validation_errors_json=[],
    )
    with pytest.raises(ValueError, match="route_outside_field_boundary"):
        update_plan_grid(plan, AgricultureGridUpdateIn(expected_revision=1, route_lonlat=[[3.9, 50.0], [4.002, 50.002]]), user_id=8)
    revision = update_plan_grid(plan, AgricultureGridUpdateIn(expected_revision=1, route_lonlat=[[4.001, 50.001], [4.002, 50.002]]), user_id=8)
    assert plan.grid_revision == 2
    assert revision.revision == 2
    assert plan.route_geojson["coordinates"] == [[4.001, 50.001], [4.002, 50.002]]
