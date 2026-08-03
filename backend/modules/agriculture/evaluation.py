"""Deterministic agriculture evaluation primitives.

These metrics are deliberately model-agnostic. Production promotion can consume
the same manifest and thresholds with labelled field/flight data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from math import hypot
from typing import Any


@dataclass(frozen=True)
class AgricultureEvaluationThresholds:
    quality_score: float = 0.85
    geospatial_error_m: float = 3.0
    confidence_known: float = 0.65
    confidence_publish: float = 0.8


def _iou(first: dict[str, float], second: dict[str, float]) -> float:
    left = max(first["x"], second["x"])
    top = max(first["y"], second["y"])
    right = min(first["x"] + first["w"], second["x"] + second["w"])
    bottom = min(first["y"] + first["h"], second["y"] + second["h"])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first["w"]) * max(0.0, first["h"])
    second_area = max(0.0, second["w"]) * max(0.0, second["h"])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def evaluate_detection_batch(*, predictions: list[dict[str, Any]], labels: list[dict[str, Any]], thresholds: AgricultureEvaluationThresholds | None = None) -> dict[str, Any]:
    policy = thresholds or AgricultureEvaluationThresholds()
    remaining = list(labels)
    true_positive = 0
    ious: list[float] = []
    geospatial_errors: list[float] = []
    for prediction in predictions:
        matches = [(_iou(prediction["box"], label["box"]), index, label) for index, label in enumerate(remaining) if prediction.get("type") == label.get("type")]
        best = max(matches, default=(0.0, -1, None))
        if best[0] >= 0.5:
            true_positive += 1
            ious.append(best[0])
            remaining.pop(best[1])
        if prediction.get("location") and best[2] and best[2].get("location"):
            geospatial_errors.append(hypot(float(prediction["location"][0]) - float(best[2]["location"][0]), float(prediction["location"][1]) - float(best[2]["location"][1])))
    false_positive = max(0, len(predictions) - true_positive)
    false_negative = len(remaining)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    return {"true_positive": true_positive, "false_positive": false_positive, "false_negative": false_negative, "precision": precision, "recall": recall, "mean_iou": sum(ious) / len(ious) if ious else 0.0, "mean_geospatial_error_m": sum(geospatial_errors) / len(geospatial_errors) if geospatial_errors else None, "publishable": precision >= policy.quality_score and (not geospatial_errors or sum(geospatial_errors) / len(geospatial_errors) <= policy.geospatial_error_m)}


def confidence_state(confidence: float, *, thresholds: AgricultureEvaluationThresholds | None = None, out_of_distribution: bool = False) -> str:
    policy = thresholds or AgricultureEvaluationThresholds()
    if out_of_distribution or confidence < policy.confidence_known:
        return "unknown"
    if confidence < policy.confidence_publish:
        return "review"
    return "publishable"


def build_dataset_manifest(*, dataset_key: str, flights: list[str], split: str, thresholds: AgricultureEvaluationThresholds | None = None, created_at: datetime | None = None) -> dict[str, Any]:
    if split not in {"train", "validation", "test", "shadow"}:
        raise ValueError("split must be train, validation, test, or shadow")
    return {"schema_version": "agriculture-evaluation-v1", "dataset_key": dataset_key, "flight_ids": sorted(set(flights)), "split": split, "thresholds": asdict(thresholds or AgricultureEvaluationThresholds()), "created_at": (created_at or datetime.now(UTC)).isoformat()}


def evaluate_predictions(predictions: list[dict[str, Any]], labels: list[dict[str, Any]]) -> dict[str, Any]:
    """Compatibility adapter for the persisted frame-box evaluation contract."""
    converted_predictions = [{"type": row.get("label"), "box": {"x": float(row.get("x1", 0)), "y": float(row.get("y1", 0)), "w": float(row.get("x2", 0)) - float(row.get("x1", 0)), "h": float(row.get("y2", 0)) - float(row.get("y1", 0))}} for row in predictions]
    converted_labels = [{"type": row.get("label"), "box": {"x": float(row.get("x1", 0)), "y": float(row.get("y1", 0)), "w": float(row.get("x2", 0)) - float(row.get("x1", 0)), "h": float(row.get("y2", 0)) - float(row.get("y1", 0))}} for row in labels]
    result = evaluate_detection_batch(predictions=converted_predictions, labels=converted_labels)
    confidence_values = [float(row.get("confidence", 0.0)) for row in predictions]
    result["calibration_mae"] = sum(abs(value - 1.0) for value in confidence_values) / len(confidence_values) if confidence_values else 0.0
    return result


def drift_report(current: dict[str, float], baseline: dict[str, float], *, warning_delta: float = 0.2) -> dict[str, Any]:
    deltas = {key: float(current[key]) - float(baseline[key]) for key in current.keys() & baseline.keys()}
    return {"status": "warning" if any(abs(value) >= warning_delta for value in deltas.values()) else "pass", "deltas": deltas, "warning_delta": warning_delta}
