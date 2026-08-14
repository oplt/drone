"""Research-only crop-vs-weed segmentation benefit gate."""

from __future__ import annotations

from typing import Any

EXPERIMENT_POLICY_VERSION = "crop-weed-segmentation-experiment.v1"


def evaluate_segmentation_experiment(payload: dict[str, Any]) -> dict[str, Any]:
    dataset = dict(payload.get("dataset") or {})
    baseline = dict(payload.get("detection_baseline") or {})
    candidate = dict(payload.get("segmentation_candidate") or {})
    reasons: list[str] = []
    if not str(dataset.get("crop_type") or "").strip():
        reasons.append("crop_specific_dataset_required")
    if int(dataset.get("labeled_images", 0) or 0) < 300:
        reasons.append("at_least_300_labeled_images_required")
    if int(dataset.get("annotated_instances", 0) or 0) < 1_000:
        reasons.append("at_least_1000_annotated_instances_required")
    if int(dataset.get("independent_fields", 0) or 0) < 3:
        reasons.append("at_least_3_independent_fields_required")
    if dataset.get("split") not in {"holdout", "test", "shadow"}:
        reasons.append("independent_holdout_split_required")
    if not str(dataset.get("source_checksum") or "").strip():
        reasons.append("dataset_checksum_required")

    required_metrics = ("weed_zone_iou", "area_mae_pct")
    metrics_missing = False
    for name, values in (("detection_baseline", baseline), ("segmentation_candidate", candidate)):
        for metric in required_metrics:
            if not isinstance(values.get(metric), (int, float)):
                reasons.append(f"{name}_{metric}_required")
                metrics_missing = True
    improvements: dict[str, float | None] = {
        "weed_zone_iou_absolute": None,
        "area_mae_relative": None,
    }
    if not metrics_missing:
        baseline_iou = float(baseline["weed_zone_iou"])
        candidate_iou = float(candidate["weed_zone_iou"])
        baseline_mae = float(baseline["area_mae_pct"])
        candidate_mae = float(candidate["area_mae_pct"])
        improvements = {
            "weed_zone_iou_absolute": candidate_iou - baseline_iou,
            "area_mae_relative": (
                (baseline_mae - candidate_mae) / baseline_mae if baseline_mae > 0 else None
            ),
        }
        if candidate_iou < 0.60:
            reasons.append("candidate_weed_zone_iou_below_0.60")
        if candidate_iou - baseline_iou < 0.05:
            reasons.append("weed_zone_iou_improvement_below_0.05")
        if baseline_mae <= 0 or (baseline_mae - candidate_mae) / baseline_mae < 0.10:
            reasons.append("area_error_improvement_below_10_percent")

    benefit_demonstrated = not reasons
    return {
        "status": "benefit_demonstrated" if benefit_demonstrated else "blocked",
        "policy_version": EXPERIMENT_POLICY_VERSION,
        "dataset_adequate": not any(
            reason.startswith(("crop_specific", "at_least", "independent", "dataset_checksum"))
            for reason in reasons
        ),
        "benefit_demonstrated": benefit_demonstrated,
        "production_eligible": False,
        "production_status": "research_only",
        "reasons": reasons,
        "dataset": dataset,
        "detection_baseline": baseline,
        "segmentation_candidate": candidate,
        "improvements": improvements,
        "next_step": (
            "architecture_and_safety_review_required_before_any_production_enablement"
            if benefit_demonstrated
            else "collect_or_improve_crop_specific_holdout_evidence"
        ),
    }
