from __future__ import annotations

import pytest

from backend.modules.agriculture.release_governance import (
    AgricultureSliceThresholds,
    SUPPORTED_CROPS,
    SUPPORTED_SENSORS,
    SUPPORTED_STAGES,
    drift_retraining_trigger,
    evaluate_shadow_release,
    resolve_thresholds,
    validate_rgb_release_evidence,
)


def _metrics() -> dict[str, float]:
    return {
        "quality_score": 0.8, "canopy_iou": 0.75, "row_accuracy": 0.9,
        "count_error": 0.05, "skip_double_precision": 0.9,
        "weed_zone_precision": 0.85, "weed_zone_recall": 0.8,
        "water_zone_precision": 0.9, "water_zone_recall": 0.8,
        "geospatial_error_m": 1.0, "area_error": 0.05,
    }


def test_thresholds_resolve_by_crop_stage_sensor_and_allow_owner_override():
    values = resolve_thresholds(crop="wheat", stage="tillering", sensor="rgb", overrides={"quality_score": 0.72})
    assert values["quality_score"] == 0.72
    assert set(values) == set(AgricultureSliceThresholds.__annotations__)
    for crop in SUPPORTED_CROPS:
        for stage in SUPPORTED_STAGES:
            for sensor in SUPPORTED_SENSORS:
                assert resolve_thresholds(crop=crop, stage=stage, sensor=sensor)["quality_score"] > 0


def test_shadow_gate_requires_all_metrics_and_blocks_regression():
    passed = evaluate_shadow_release(candidate={"metrics": _metrics()}, incumbent={"quality_score": 0.79}, thresholds=resolve_thresholds(crop="wheat", stage="tillering", sensor="rgb"))
    assert passed["publishable"] is True
    blocked = evaluate_shadow_release(candidate={"metrics": {"quality_score": 0.3}}, incumbent={}, thresholds=resolve_thresholds(crop="wheat", stage="tillering", sensor="rgb"))
    assert blocked["status"] == "blocked"
    assert "missing:canopy_iou" in blocked["failures"]


def test_drift_monitor_emits_retraining_trigger_for_slice_drift():
    result = drift_retraining_trigger(current={"precision": 0.5}, baseline={"precision": 0.9}, slices={"corn:flowering:thermal": {"precision": 0.4}})
    assert result["status"] == "retrain"
    assert result["retraining_triggered"] is True


def test_threshold_dataclass_keeps_defaults_sane():
    values = AgricultureSliceThresholds()
    assert 0 <= values.quality_score <= 1
    assert values.geospatial_error_m >= 0


def test_rgb_release_evidence_requires_artifact_dataset_holdout_and_review_agreement():
    blocked = validate_rgb_release_evidence(model={"artifact_uri": None, "dataset_key": "wheat-rgb", "config": {}}, report={"metrics": {}}, dataset=None, crop_type="wheat", growth_stage="tillering")
    assert blocked["publishable"] is False
    assert "missing:artifact_digest" in blocked["failures"]
    passed = validate_rgb_release_evidence(
        model={"artifact_uri": "s3://models/wheat.onnx", "dataset_key": "wheat-rgb", "config": {"artifact_digest": "a" * 64}},
        report={"metrics": {"human_review_agreement": 0.9}},
        dataset={"status": "completed", "manifest": {"split": "shadow", "holdout_field_count": 4, "crop_types": ["wheat"], "growth_stages": ["tillering"], "sensor_type": "rgb"}},
        crop_type="wheat", growth_stage="tillering",
    )
    assert passed["publishable"] is True
