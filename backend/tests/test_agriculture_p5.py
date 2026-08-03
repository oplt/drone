import io
import json
import zipfile

from backend.modules.agriculture.p5_policy import build_csv, build_geojson, build_pdf, build_shapefile_zip, plan_inspection_waypoints


def _candidate(identifier, lon=4.0, lat=50.0, severity=.9, confidence=.9):
    return {"id": identifier, "issue_type": "crop_stress_signature", "geometry_geojson": {"type": "Polygon", "coordinates": [[[lon, lat], [lon + .001, lat], [lon + .001, lat + .001], [lon, lat], [lon, lat]]]}, "severity": severity, "confidence": confidence, "area_m2": 100, "source_ids": [identifier], "rationale": "confirmed"}


def test_inspection_planner_ranks_and_enforces_field_no_go_and_battery():
    plan = plan_inspection_waypoints([_candidate("inside"), _candidate("outside", lon=5), _candidate("no-go", lon=4.002, lat=50.002), _candidate("third", lon=4.006)], field_boundary={"type": "Polygon", "coordinates": [[[3.9, 49.9], [4.01, 49.9], [4.01, 50.01], [3.9, 50.01], [3.9, 49.9]]]}, no_go_geometries=[{"type": "Polygon", "coordinates": [[[4.0015, 50.0015], [4.004, 50.0015], [4.004, 50.004], [4.0015, 50.004], [4.0015, 50.0015]]]}], max_actions=10, battery_budget_s=90, seconds_per_action=90)
    assert plan["status"] == "ready"
    assert [row["id"] for row in plan["actions"]] == ["inside"]
    assert {row["reason"] for row in plan["rejected"]} >= {"outside_field_boundary", "inside_no_go_geometry", "battery_or_action_budget"}


def test_exports_are_reproducible_formats_with_metadata_boundary():
    payload = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [4, 50]}, "properties": {"id": "a1", "issue_type": "weed", "severity": .8, "confidence": .7, "status": "approved", "source_ids": ["obs-1"]}}], "metadata": {"run_id": "run-1", "uncertainty": "recorded"}}
    assert json.loads(build_geojson(payload))["metadata"]["run_id"] == "run-1"
    assert b"issue_type" in build_csv(payload)
    assert build_pdf(payload).startswith(b"%PDF-1.4")
    with zipfile.ZipFile(io.BytesIO(build_shapefile_zip(payload))) as archive:
        assert {"agriculture.shp", "agriculture.shx", "agriculture.dbf", "agriculture.prj"}.issubset(set(archive.namelist()))
