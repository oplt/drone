from types import SimpleNamespace

from backend.modules.agriculture.report_service import build_report_snapshot


def test_report_snapshot_is_deterministic_for_same_run_data():
    run = SimpleNamespace(
        id="run-1",
        flight_id="flight-1",
        status="review",
        progress=1.0,
        quality_gate={"status": "pass"},
        counters={"frames": 2},
        model_versions={"rgb": "candidate"},
        calibration_versions={},
    )
    observation = SimpleNamespace(
        id="observation-1",
        observation_type="water_candidate",
        review_state="unreviewed",
        geometry_geojson={"type": "Point", "coordinates": [4.3, 50.8]},
        severity=0.8,
        confidence=0.7,
        model_version="rgb-heuristic-v1",
        source_ids=["frame-1"],
        uncertainty={"candidate": True},
    )
    layer = SimpleNamespace(
        layer_name="water", status="partial", checksum="layer-sha", summary={"count": 1}
    )
    first, first_checksum = build_report_snapshot(
        run=run, observations=[observation], layers=[layer], template_key="standard"
    )
    _second, second_checksum = build_report_snapshot(
        run=run, observations=[observation], layers=[layer], template_key="standard"
    )
    assert first_checksum == second_checksum
    assert first["summary"]["observation_count"] == 1
    assert first["features"][0]["properties"]["uncertainty"]["candidate"] is True


def test_report_snapshot_preserves_review_and_model_provenance():
    run = SimpleNamespace(
        id="run-2",
        flight_id="flight-2",
        status="review",
        progress=1.0,
        quality_gate={},
        counters={},
        model_versions={},
        calibration_versions={},
    )
    observation = SimpleNamespace(
        id="observation-2",
        observation_type="row",
        review_state="confirmed",
        geometry_geojson={},
        severity=0.2,
        confidence=0.9,
        model_version="row-v2",
        source_ids=[],
        uncertainty={},
    )
    snapshot, _ = build_report_snapshot(
        run=run, observations=[observation], layers=[], template_key="executive"
    )
    props = snapshot["features"][0]["properties"]
    assert props["review_state"] == "confirmed"
    assert props["model_version"] == "row-v2"
    assert snapshot["template_key"] == "executive"
