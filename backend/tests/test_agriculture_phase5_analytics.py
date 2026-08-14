from types import SimpleNamespace

import pytest

from backend.modules.agriculture.aggregation import aggregate_detections
from backend.modules.agriculture.capabilities import (
    CAPABILITIES,
    AgricultureCapabilityReleaseService,
)
from backend.modules.agriculture.inference_profiles import default_inference_profile
from backend.modules.agriculture.segmentation_experiment import evaluate_segmentation_experiment
from backend.modules.agriculture.stand import summarize_stands
from backend.modules.agriculture.weed_density import build_weed_density
from backend.modules.vision_models.contracts import VisionModelRelease


def _detection(
    index: int, label: str, *, x_m: float, y_m: float = 0.0, track_id: int | None = None
):
    return SimpleNamespace(
        id=f"d-{index}",
        job_id="job-1",
        label=label,
        confidence=0.9,
        lon=4.0 + x_m / 71_554,
        lat=50.0 + y_m / 110_574,
        track_id=index if track_id is None else track_id,
        timestamp_seconds=float(index),
        raw={"telemetry_match_quality": "exact"},
    )


def test_stand_gap_requires_explicit_crop_spacing_and_emits_metric_polygon():
    rows = [
        _detection(1, "plant", x_m=0),
        _detection(2, "plant", x_m=0.5),
        _detection(3, "plant", x_m=2.5),
    ]
    blocked = summarize_stands(rows, row_spacing_m=1, row_direction_deg=0)
    assert blocked["gap_status"] == "blocked"
    assert "expected_plant_spacing_m_missing" in blocked["quality_warnings"]

    result = summarize_stands(
        rows,
        row_spacing_m=1,
        row_direction_deg=0,
        expected_plant_spacing_m=0.5,
        crop_type="corn",
        gap_multiplier=1.75,
    )
    assert result["gap_status"] == "pass"
    assert result["spacing"]["median_spacing_m"] > 0
    assert len(result["gaps"]) == 1
    assert result["gaps"][0]["geometry_geojson"]["type"] == "Polygon"
    assert result["gaps"][0]["affected_area_m2"] > 0


def test_weed_density_is_metric_ranked_and_compares_explicit_baseline():
    weeds = [
        _detection(1, "weed", x_m=2, y_m=2),
        _detection(2, "weed", x_m=3, y_m=3),
        _detection(3, "weed", x_m=17, y_m=17),
    ]
    boundary = {
        "type": "Polygon",
        "coordinates": [
            [
                [4.0, 50.0],
                [4.0 + 20 / 71_554, 50.0],
                [4.0 + 20 / 71_554, 50.0 + 20 / 110_574],
                [4.0, 50.0 + 20 / 110_574],
                [4.0, 50.0],
            ]
        ],
    }
    result = build_weed_density(
        weeds,
        field_boundary_geojson=boundary,
        cell_size_m=10,
        hotspot_percentile=0.75,
        previous_density_per_m2=0.001,
        previous_flight_id="flight-before",
    )
    assert result["status"] == "pass"
    assert result["summary"]["units"] == "detections/m²"
    assert result["summary"]["hotspot_count"] >= 1
    assert result["summary"]["change_vs_previous"]["previous_flight_id"] == "flight-before"
    assert all(
        feature["geometry"]["type"] in {"Polygon", "MultiPolygon"}
        for feature in result["geojson"]["features"]
    )


def test_segmentation_experiment_never_self_enables_production():
    result = evaluate_segmentation_experiment(
        {
            "dataset": {
                "crop_type": "corn",
                "labeled_images": 500,
                "annotated_instances": 2_000,
                "independent_fields": 4,
                "split": "holdout",
                "source_checksum": "a" * 64,
            },
            "detection_baseline": {"weed_zone_iou": 0.55, "area_mae_pct": 20},
            "segmentation_candidate": {"weed_zone_iou": 0.65, "area_mae_pct": 15},
        }
    )
    assert result["benefit_demonstrated"] is True
    assert result["dataset_adequate"] is True
    assert result["production_eligible"] is False
    assert result["production_status"] == "research_only"


def test_crop_specific_detection_capabilities_have_distinct_observation_types():
    rows = [_detection(1, "ripe_tomato", x_m=1)]
    result = aggregate_detections(
        rows,
        capability_by_job_id={"job-1": "ripeness_classification"},
    )
    assert result[0]["observation_type"] == "ripeness_classification"


def test_fruit_counting_defaults_to_tracking_and_reports_unique_visible_tracks():
    rows = [
        _detection(1, "tomato", x_m=1, track_id=11),
        _detection(2, "tomato", x_m=1.1, track_id=11),
        _detection(3, "tomato", x_m=1.2, track_id=12),
    ]
    result = aggregate_detections(
        rows,
        capability_by_job_id={"job-1": "fruit_counting"},
    )
    assert default_inference_profile("fruit_counting")["tracking_enabled"] is True
    assert result[0]["observation_type"] == "fruit_count"
    assert result[0]["sensor_values"]["visible_fruit_count"] == 2
    assert result[0]["sensor_values"]["count_status"] == "pass"


@pytest.mark.asyncio
async def test_ripeness_release_requires_named_crop_and_strong_per_class_evidence():
    version = VisionModelRelease(
        version_id="version-1",
        status="production",
        model_id="model-1",
        model_name="ripeness",
        model_version=1,
        model_checksum="b" * 64,
        dataset_id="dataset-1",
        crop="generic",
        classes=("ripe", "unripe"),
        evaluation_metrics={
            "summary": {"map50": 0.8, "precision": 0.8, "recall": 0.8},
            "per_class": [
                {"class_name": "ripe", "map50": 0.7},
                {"class_name": "unripe", "map50": 0.7},
            ],
        },
        capability_id="ripeness_classification",
        project_org_id=7,
        project_created_by_user_id=3,
    )
    with pytest.raises(ValueError, match="single named crop"):
        await AgricultureCapabilityReleaseService().activate_for_model_version(
            SimpleNamespace(), version=version, org_id=7, user_id=3
        )
    capability = CAPABILITIES["ripeness_classification"]
    assert capability.crop_specific is True
    assert capability.capture_conditions["camera_calibration_required"] is True
    assert any("arbitrary RGB" in limitation for limitation in capability.limitations)


@pytest.mark.asyncio
async def test_ripeness_release_requires_holdout_metrics_for_every_output_class():
    version = VisionModelRelease(
        version_id="version-2",
        status="production",
        model_id="model-2",
        model_name="tomato-ripeness",
        model_version=1,
        model_checksum="c" * 64,
        dataset_id="dataset-2",
        crop="tomato",
        classes=("ripe", "unripe"),
        evaluation_metrics={
            "summary": {"map50": 0.8, "precision": 0.8, "recall": 0.8},
            "per_class": [{"class_name": "ripe", "map50": 0.7}],
        },
        capability_id="ripeness_classification",
        project_org_id=7,
        project_created_by_user_id=3,
    )
    with pytest.raises(ValueError, match="Every output class"):
        await AgricultureCapabilityReleaseService().activate_for_model_version(
            SimpleNamespace(), version=version, org_id=7, user_id=3
        )
