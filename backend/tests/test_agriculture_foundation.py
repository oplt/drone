import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.entrypoints.api.app import app
from backend.modules.agriculture.aggregation import aggregate_detections
from backend.modules.agriculture.georeferencing import Pose, frame_footprint, interpolate_pose
from backend.modules.agriculture.policy import agriculture_validator
from backend.modules.agriculture.schemas import (
    AgricultureMissionProfile,
    AnalysisRunIn,
    FrameManifestItem,
    MediaManifestIn,
    TelemetrySampleIn,
)
from backend.modules.agriculture.service import agriculture_service, geometry_4326, polygon_area_m2
from backend.modules.agriculture.storage import AgricultureStorage
from backend.entrypoints.workers.celery_app import CELERY_AGRICULTURE_QUEUES, celery_app


@dataclass
class Sample:
    timestamp_utc: datetime
    lat: float
    lon: float
    relative_altitude_m: float | None = 30.0
    absolute_altitude_m: float | None = None
    roll_deg: float | None = None
    pitch_deg: float | None = None
    yaw_deg: float | None = None
    gps_quality: float | None = 90.0


def test_agriculture_routes_are_registered():
    paths = {route.path for route in app.routes}
    assert "/agriculture/flights/plan-preview" in paths
    assert "/agriculture/flights/{flight_id}/frame-manifest" in paths
    assert "/agriculture/fields/{field_id}/timeline" in paths
    assert "/agriculture/analysis-runs/{run_id}/cancel" in paths
    assert "/agriculture/analysis-runs/{run_id}/replay" in paths
    assert "/agriculture/observations/{observation_id}/evidence" in paths
    assert "/agriculture/flights/{flight_id}/publish" in paths
    assert "/agriculture/flights/{flight_id}/archive" in paths
    assert "/agriculture/flights/start" in paths
    assert "/agriculture/flights/{flight_id}/manifests" in paths
    assert "/agriculture/fields/{field_id}/comparisons" in paths
    assert "/agriculture/comparisons/{comparison_id}" in paths
    assert "/agriculture/comparisons/{comparison_id}/layers/{layer}" in paths
    assert "/agriculture/comparisons/{comparison_id}/trends" in paths


def test_agriculture_v1_openapi_contract_has_filters_examples_and_queued_statuses():
    spec = app.openapi()
    observations = spec["paths"]["/agriculture/analysis-runs/{run_id}/observations"]["get"]
    parameters = {item["name"] for item in observations["parameters"]}
    assert {"bbox", "trend", "detected_from", "detected_to", "cursor", "limit"} <= parameters
    assert observations["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("AgricultureObservationPage")
    assert "examples" in spec["components"]["schemas"]["TelemetryBatchIn"]
    assert "202" in spec["paths"]["/agriculture/flights/start"]["post"]["responses"]
    assert (
        "202"
        in spec["paths"]["/agriculture/flights/{flight_id}/analysis-runs"]["post"]["responses"]
    )


def test_telemetry_contract_rejects_nan_and_normalizes_offset_input():
    with pytest.raises(ValueError):
        TelemetrySampleIn(timestamp=datetime.now(UTC), lat=float("nan"), lon=4.0)
    assert TelemetrySampleIn(timestamp=datetime.now(UTC), lat=50.0, lon=4.0).source == "upload"
    assert TelemetrySampleIn(
        timestamp=datetime.now(UTC), lat=50.0, lon=4.0, camera_trigger=True
    ).camera_trigger


def test_canonical_media_frame_and_run_contracts_are_complete():
    media = MediaManifestIn(
        source_kind="multispectral_band",
        storage_key="org/1/flights/f/media.tif",
        checksum="a" * 64,
        codec="geotiff",
    )
    frame = FrameManifestItem(
        frame_index=3,
        timestamp=datetime.now(UTC),
        pose_interpolation_status="interpolated",
        footprint_geojson={
            "type": "Polygon",
            "coordinates": [[[4, 50], [4.001, 50], [4.001, 50.001], [4, 50]]],
        },
    )
    run = AnalysisRunIn(
        idempotency_key="canonical-run",
        analysis_profile={"name": "crop-health-v1"},
        parameters={"threshold": 0.7},
    )
    assert media.codec == "geotiff"
    assert frame.pose_interpolation_status == "interpolated"
    assert geometry_4326(frame.footprint_geojson) is not None
    assert run.analysis_profile["name"] == "crop-health-v1"


def test_frame_detections_are_deduplicated_before_farmer_output():
    rows = [
        SimpleNamespace(
            id="a",
            label="weed",
            timestamp_seconds=1.0,
            lon=4.0,
            lat=50.0,
            confidence=0.8,
            track_id="track-1",
            raw={},
        ),
        SimpleNamespace(
            id="b",
            label="weed",
            timestamp_seconds=2.0,
            lon=4.000001,
            lat=50.000001,
            confidence=0.9,
            track_id="track-1",
            raw={},
        ),
    ]
    observations = aggregate_detections(rows)
    assert len(observations) == 1
    assert observations[0]["uncertainty"]["deduplication"] == "track_id_or_spatial_cluster"
    assert observations[0]["evidence_ids"] == ["a", "b"]


def test_pose_interpolation_and_gap_are_explicit():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [Sample(start, 50.0, 4.0), Sample(start + timedelta(seconds=2), 50.0002, 4.0002)]
    result = interpolate_pose(rows, start + timedelta(seconds=1))
    assert result.status == "interpolated"
    assert result.pose is not None and result.pose.lat == pytest.approx(50.0001)
    gap = interpolate_pose(rows, start + timedelta(seconds=20))
    assert gap.status == "gap"
    assert gap.pose is None


def test_footprint_resolves_only_with_altitude_and_area_uses_meters():
    pose = Pose(datetime.now(UTC), 50.0, 4.0, 30.0, None, None, 0.0, 90.0)
    footprint = frame_footprint(
        pose=pose, width_px=4000, height_px=3000, fov_h_deg=78, fov_v_deg=62
    )
    assert footprint["status"] == "resolved"
    unresolved = frame_footprint(
        pose=Pose(pose.timestamp_utc, 50, 4, None, None, None, None, None),
        width_px=1,
        height_px=1,
        fov_h_deg=78,
        fov_v_deg=62,
    )
    assert unresolved["status"] == "unresolved"
    assert polygon_area_m2([[4.0, 50.0], [4.001, 50.0], [4.001, 50.001], [4.0, 50.0]]) > 0


def test_profile_policy_requires_calibration_for_multispectral_and_rejects_bad_polygon():
    profile = AgricultureMissionProfile(
        preset="multispectral_thermal", sensor_inventory=["multispectral"]
    )
    result = agriculture_validator.validate(
        profile=profile,
        cruise_alt_m=30,
        field_polygon_lonlat=[[4, 50], [4.001, 50.001], [4, 50.001]],
    )
    assert not result.valid
    assert "multispectral_thermal_preset_requires_both_sensors" in result.errors
    assert "camera_calibration_required_for_selected_sensor" in result.errors


def test_agriculture_profile_contains_reproducible_camera_contract():
    profile = AgricultureMissionProfile(focal_length_mm=24, grid_angle_deg=15)
    assert profile.camera_resolution_width_px == 4000
    assert profile.camera_resolution_height_px == 3000
    assert profile.focal_length_mm == 24
    assert profile.flight_kind == "agriculture_survey"


def test_agriculture_flight_lifecycle_rejects_skipped_states():
    class Db:
        async def flush(self):
            return None

    flight = SimpleNamespace(status="running", started_at=datetime.now(UTC), ended_at=None)
    asyncio.run(agriculture_service.transition_flight(Db(), flight=flight, target="captured"))
    assert flight.status == "captured" and flight.ended_at is not None
    with pytest.raises(ValueError, match="Invalid agriculture flight transition"):
        asyncio.run(agriculture_service.transition_flight(Db(), flight=flight, target="published"))


def test_storage_rejects_path_traversal_and_signed_access_never_reads_outside_root(tmp_path):
    storage = AgricultureStorage(tmp_path)
    with pytest.raises(ValueError):
        storage.validate_key("../../etc/passwd")


def test_agriculture_storage_sniffs_mime_and_backup_restore_is_checksum_verified(tmp_path):
    storage = AgricultureStorage(tmp_path)
    source = storage.safe_path("org/1/flights/f/image.jpg")
    source.parent.mkdir(parents=True)
    source.write_bytes(b"\xff\xd8\xff" + b"image-data")
    checksum = storage.checksum("org/1/flights/f/image.jpg")
    assert storage.validate_file_content("org/1/flights/f/image.jpg", declared_content_type="image/jpeg") == "image/jpeg"
    with pytest.raises(ValueError, match="MIME"):
        storage.validate_file_content("org/1/flights/f/image.jpg", declared_content_type="image/png")
    storage.backup("org/1/flights/f/image.jpg", backup_key="backups/agriculture/1/image.jpg")
    storage.restore("backups/agriculture/1/image.jpg", target_key="org/1/restored/image.jpg", expected_checksum=checksum)
    assert storage.checksum("org/1/restored/image.jpg") == checksum


def test_agriculture_stage_queues_are_dedicated_and_registered():
    assert set(CELERY_AGRICULTURE_QUEUES) == {"ingest", "quality", "rgb_inference", "segmentation", "geospatial_aggregation", "temporal_comparison", "sensor_fusion", "exports", "dead_letter"}
    for stage in ("ingest", "quality", "rgb_inference", "segmentation", "geospatial_aggregation", "temporal_comparison", "sensor_fusion", "exports"):
        assert f"agriculture.stage.{stage}" in celery_app.tasks
    assert "agriculture.dead_letter" in celery_app.tasks
