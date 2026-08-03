import pytest

from backend.modules.agriculture.evaluation import AgricultureEvaluationThresholds, build_dataset_manifest, confidence_state, evaluate_detection_batch


def test_evaluation_is_deterministic_and_reports_publish_gate():
    result = evaluate_detection_batch(
        predictions=[{"type": "weed", "box": {"x": 0, "y": 0, "w": 10, "h": 10}, "location": [1, 1]}],
        labels=[{"type": "weed", "box": {"x": 0, "y": 0, "w": 10, "h": 10}, "location": [1, 2]}],
        thresholds=AgricultureEvaluationThresholds(quality_score=0.9, geospatial_error_m=2),
    )
    assert result["precision"] == 1.0
    assert result["mean_iou"] == 1.0
    assert result["publishable"] is True


def test_confidence_abstains_for_unknown_or_low_confidence():
    assert confidence_state(0.2) == "unknown"
    assert confidence_state(0.7) == "review"
    assert confidence_state(0.95, out_of_distribution=True) == "unknown"


def test_dataset_manifest_requires_versioned_split():
    manifest = build_dataset_manifest(dataset_key="wheat-v1", flights=["f2", "f1", "f1"], split="shadow")
    assert manifest["flight_ids"] == ["f1", "f2"]
    with pytest.raises(ValueError):
        build_dataset_manifest(dataset_key="wheat-v1", flights=[], split="random")
