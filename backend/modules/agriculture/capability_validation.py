"""Crop-specific release evidence gates for agriculture capabilities."""

from __future__ import annotations

from collections.abc import Mapping

from backend.modules.vision_models.contracts import VisionModelRelease


def specialized_release_failures(
    *,
    crop_specific: bool,
    evaluation_thresholds: Mapping[str, float],
    version: VisionModelRelease,
) -> list[str]:
    if not crop_specific:
        return []
    failures: list[str] = []
    crop = str(version.crop or "").strip().lower()
    if crop in {"", "generic", "general", "all", "mixed", "unknown"}:
        failures.append("A single named crop is required for this capability")
    summary = version.evaluation_metrics.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    for metric, threshold in evaluation_thresholds.items():
        if metric == "per_class_map50":
            per_class = version.evaluation_metrics.get("per_class")
            if not isinstance(per_class, list) or not per_class:
                failures.append("Per-class holdout evaluation is required")
            else:
                metrics_by_class = {
                    str(row.get("class_name")): row.get("map50")
                    for row in per_class
                    if isinstance(row, dict) and row.get("class_name")
                }
                if set(version.classes) - set(metrics_by_class):
                    failures.append("Every output class requires holdout evaluation")
                elif any(
                    not isinstance(metrics_by_class[name], (int, float))
                    or float(metrics_by_class[name]) < threshold
                    for name in version.classes
                ):
                    failures.append(f"Every class requires map50 >= {threshold:g}")
            continue
        value = summary.get(metric)
        if not isinstance(value, (int, float)) or float(value) < threshold:
            failures.append(f"Holdout {metric} must be >= {threshold:g}")
    if not version.classes:
        failures.append("At least one explicit output class is required")
    return failures
