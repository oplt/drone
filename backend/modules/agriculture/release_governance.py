"""Release gates for agriculture models and slice-specific quality evidence."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
import re


METRIC_KEYS = (
    "quality_score", "canopy_iou", "row_accuracy", "count_error",
    "skip_double_precision", "weed_zone_precision", "weed_zone_recall",
    "water_zone_precision", "water_zone_recall", "geospatial_error_m",
    "area_error",
)
SUPPORTED_CROPS = ("wheat", "corn", "potato")
SUPPORTED_STAGES = ("seedling", "tillering", "flowering", "maturity")
SUPPORTED_SENSORS = ("rgb", "multispectral", "thermal")


@dataclass(frozen=True)
class AgricultureSliceThresholds:
    quality_score: float = 0.60
    canopy_iou: float = 0.65
    row_accuracy: float = 0.80
    count_error: float = 0.15
    skip_double_precision: float = 0.80
    weed_zone_precision: float = 0.75
    weed_zone_recall: float = 0.70
    water_zone_precision: float = 0.80
    water_zone_recall: float = 0.70
    geospatial_error_m: float = 3.0
    area_error: float = 0.15


def threshold_matrix() -> dict[str, dict[str, dict[str, float]]]:
    """Return explicit crop/stage/sensor defaults, overridable by product owners."""
    default = asdict(AgricultureSliceThresholds())
    return {
        crop: {stage: {sensor: default.copy() for sensor in SUPPORTED_SENSORS} for stage in SUPPORTED_STAGES}
        for crop in SUPPORTED_CROPS
    } | {"default": {"default": {"default": default}}}


def resolve_thresholds(*, crop: str | None, stage: str | None, sensor: str | None, overrides: dict[str, Any] | None = None) -> dict[str, float]:
    matrix = threshold_matrix()
    crop_values = matrix.get((crop or "").lower(), matrix["default"])
    stage_values = crop_values.get((stage or "").lower(), crop_values.get("default", {}))
    values = stage_values.get((sensor or "").lower(), stage_values.get("default", {})).copy()
    values.update({key: float(value) for key, value in (overrides or {}).items() if key in METRIC_KEYS})
    return values


def evaluate_shadow_release(*, candidate: dict[str, Any], incumbent: dict[str, Any] | None, thresholds: dict[str, float]) -> dict[str, Any]:
    """Gate a candidate on holdout/shadow metrics and prevent silent regressions."""
    metrics = candidate.get("metrics") or {}
    failures: list[str] = []
    for key, minimum in thresholds.items():
        if key not in metrics:
            failures.append(f"missing:{key}")
            continue
        value = float(metrics[key])
        passed = value <= minimum if key in {"count_error", "geospatial_error_m", "area_error"} else value >= minimum
        if not passed:
            failures.append(f"below_threshold:{key}")
    regressions: list[str] = []
    for key, old_value in (incumbent or {}).items():
        if key in metrics and isinstance(old_value, (int, float)) and float(metrics[key]) < float(old_value) * 0.95:
            regressions.append(f"regression:{key}")
    return {
        "status": "pass" if not failures and not regressions else "blocked",
        "publishable": not failures and not regressions,
        "failures": failures,
        "regressions": regressions,
        "thresholds": thresholds,
        "metrics": metrics,
        "evaluation_kind": "shadow",
    }


def validate_rgb_release_evidence(*, model: dict[str, Any], report: dict[str, Any], dataset: dict[str, Any] | None, crop_type: str | None, growth_stage: str | None, sensor_type: str | None = "rgb") -> dict[str, Any]:
    """Validate the non-metric evidence required before an RGB model can publish."""
    failures: list[str] = []
    config = model.get("config") or {}
    artifact_uri = str(model.get("artifact_uri") or "").strip()
    artifact_digest = str(config.get("artifact_digest") or "").strip().lower()
    if not artifact_uri:
        failures.append("missing:artifact_uri")
    if not re.fullmatch(r"[a-f0-9]{64}", artifact_digest):
        failures.append("missing:artifact_digest")
    if not model.get("dataset_key"):
        failures.append("missing:model_dataset_key")
    if dataset is None:
        failures.append("missing:dataset_manifest")
    else:
        manifest = dataset.get("manifest") or {}
        if dataset.get("status") != "completed":
            failures.append("dataset:not_completed")
        if manifest.get("split") not in {"test", "shadow", "holdout"}:
            failures.append("dataset:not_holdout_split")
        if int(manifest.get("holdout_field_count", 0) or 0) < 3:
            failures.append("dataset:holdout_field_count_lt_3")
        scopes = manifest.get("crop_types") or manifest.get("crops") or []
        if crop_type and scopes and crop_type not in scopes:
            failures.append("dataset:crop_scope_mismatch")
        stages = manifest.get("growth_stages") or manifest.get("stages") or []
        if growth_stage and stages and growth_stage not in stages:
            failures.append("dataset:growth_stage_scope_mismatch")
        if manifest.get("sensor_type", sensor_type) != sensor_type:
            failures.append("dataset:sensor_scope_mismatch")
    metrics = report.get("metrics") or {}
    agreement = metrics.get("human_review_agreement", config.get("human_review_agreement"))
    if agreement is None or float(agreement) < 0.80:
        failures.append("missing:human_review_agreement")
    return {"publishable": not failures, "status": "pass" if not failures else "blocked", "failures": failures, "scope": {"crop_type": crop_type, "growth_stage": growth_stage, "sensor_type": sensor_type}, "artifact_digest": artifact_digest or None}


def drift_retraining_trigger(*, current: dict[str, float], baseline: dict[str, float], slices: dict[str, dict[str, float]] | None = None, warning_delta: float = 0.20, retrain_delta: float = 0.35) -> dict[str, Any]:
    deltas = {key: float(current[key]) - float(baseline[key]) for key in current.keys() & baseline.keys()}
    slice_deltas: dict[str, dict[str, float]] = {}
    for slice_name, values in (slices or {}).items():
        slice_deltas[slice_name] = {key: float(value) - float(baseline.get(key, value)) for key, value in values.items()}
    all_deltas = [abs(value) for value in deltas.values()]
    all_deltas.extend(abs(value) for values in slice_deltas.values() for value in values.values())
    maximum = max(all_deltas, default=0.0)
    return {
        "status": "retrain" if maximum >= retrain_delta else "warning" if maximum >= warning_delta else "pass",
        "retraining_triggered": maximum >= retrain_delta,
        "maximum_delta": maximum,
        "warning_delta": warning_delta,
        "retrain_delta": retrain_delta,
        "deltas": deltas,
        "slice_deltas": slice_deltas,
    }
