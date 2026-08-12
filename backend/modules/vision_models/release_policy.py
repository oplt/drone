from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

POLICY_VERSION = "vision-release-policy.v2"
KNOWN_CAPABILITIES = {
    "object_detection",
    "stand_count",
    "weed_detection",
    "crop_health",
    "canopy_cover",
    "row_detection",
    "standing_water",
}

# Optional metric floors are capability overrides only — defaults require map50 alone.
DEFAULT_MAX_MAP50_REGRESSION = 0.05
CAPABILITY_METRIC_OVERRIDES: dict[str, dict[str, float]] = {
    # Example: tighten weed_detection when product policy requires it.
    # "weed_detection": {"min_map50": 0.35, "min_recall": 0.4},
}


@dataclass(frozen=True)
class MetricPolicy:
    min_map50: float
    min_map50_95: float | None = None
    min_precision: float | None = None
    min_recall: float | None = None
    min_per_class_map50: float | None = None
    max_map50_regression: float = DEFAULT_MAX_MAP50_REGRESSION


@dataclass(frozen=True)
class ReleasePolicyResult:
    eligible: bool
    reasons: tuple[str, ...]
    metrics_snapshot: dict[str, Any]
    policy_version: str = POLICY_VERSION
    inference_contract: dict[str, Any] = field(default_factory=dict)


def resolve_metric_policy(
    capability_id: str,
    *,
    minimum_map50: float,
    max_map50_regression: float | None = None,
) -> MetricPolicy:
    overrides = CAPABILITY_METRIC_OVERRIDES.get(capability_id, {})
    return MetricPolicy(
        min_map50=float(overrides.get("min_map50", minimum_map50)),
        min_map50_95=_optional_float(overrides.get("min_map50_95")),
        min_precision=_optional_float(overrides.get("min_precision")),
        min_recall=_optional_float(overrides.get("min_recall")),
        min_per_class_map50=_optional_float(overrides.get("min_per_class_map50")),
        max_map50_regression=float(
            overrides.get(
                "max_map50_regression",
                (
                    max_map50_regression
                    if max_map50_regression is not None
                    else DEFAULT_MAX_MAP50_REGRESSION
                ),
            )
        ),
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _metric_number(snapshot: dict[str, Any], key: str) -> float | None:
    value = snapshot.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def build_inference_contract(
    *,
    capability_id: str,
    task_type: str | None,
    classes: list[str] | tuple[str, ...] | None,
    model_checksum: str,
    dataset_checksum: str | None,
    metrics_snapshot: dict[str, Any],
    policy_version: str = POLICY_VERSION,
) -> dict[str, Any]:
    return {
        "capability_id": capability_id,
        "task_type": task_type or "detection",
        "classes": list(classes or ()),
        "model_checksum": model_checksum,
        "dataset_checksum": dataset_checksum,
        "evaluation_metrics": dict(metrics_snapshot),
        "policy_version": policy_version,
    }


def evaluate_release(
    *,
    status: str,
    metrics: dict[str, Any],
    weights_uri: str,
    checksum: str,
    capability_id: str,
    minimum_map50: float,
    training_run_id: str | None = None,
    dataset_id: str | None = None,
    dataset_version: int | None = None,
    dataset_manifest_checksum: str | None = None,
    test_count: int | None = None,
    artifact_verified: bool | None = None,
    production_map50: float | None = None,
    max_map50_regression: float | None = None,
    task_type: str | None = None,
    classes: list[str] | tuple[str, ...] | None = None,
) -> ReleasePolicyResult:
    """Evaluate the bounded, server-owned policy used by every promotion."""
    reasons: list[str] = []
    summary = metrics.get("summary")
    snapshot = dict(summary) if isinstance(summary, dict) else {}
    policy = resolve_metric_policy(
        capability_id,
        minimum_map50=minimum_map50,
        max_map50_regression=max_map50_regression,
    )
    map50 = _metric_number(snapshot, "map50")

    if status != "candidate":
        reasons.append("model version must be a candidate")
    if not weights_uri or not checksum:
        reasons.append("model artifact weights and checksum are required")
    if artifact_verified is False:
        reasons.append("model artifact checksum could not be verified against file")
    if capability_id not in KNOWN_CAPABILITIES:
        reasons.append("model capability is not recognized")

    if not training_run_id:
        reasons.append("training run lineage is required")
    if not dataset_id:
        reasons.append("dataset lineage is required")
    if dataset_version is not None and int(dataset_version) <= 0:
        reasons.append("dataset version lineage is invalid")
    if test_count is not None and int(test_count) <= 0:
        reasons.append("evaluation test set must be non-empty")
    if not isinstance(summary, dict) or map50 is None:
        reasons.append("evaluation result with map50 is required")
    elif map50 < policy.min_map50:
        reasons.append(f"evaluation map50 must be at least {policy.min_map50:g}")

    for key, floor in (
        ("map50_95", policy.min_map50_95),
        ("precision", policy.min_precision),
        ("recall", policy.min_recall),
    ):
        if floor is None:
            continue
        value = _metric_number(snapshot, key)
        if value is None or value < floor:
            reasons.append(f"evaluation {key} must be at least {floor:g}")

    if policy.min_per_class_map50 is not None:
        per_class = metrics.get("per_class")
        if not isinstance(per_class, list) or not per_class:
            reasons.append("per-class evaluation metrics are required")
        else:
            for row in per_class:
                if not isinstance(row, dict):
                    reasons.append("per-class evaluation metrics are invalid")
                    break
                class_map50 = _metric_number(row, "map50")
                if class_map50 is None or class_map50 < policy.min_per_class_map50:
                    name = row.get("class_name") or row.get("class_index") or "unknown"
                    reasons.append(
                        f"per-class map50 for {name} must be at least "
                        f"{policy.min_per_class_map50:g}"
                    )
                    break

    if (
        production_map50 is not None
        and map50 is not None
        and (production_map50 - map50) > policy.max_map50_regression
    ):
        reasons.append(
            "map50 regression exceeds "
            f"{policy.max_map50_regression:g} versus current production"
        )

    contract = build_inference_contract(
        capability_id=capability_id,
        task_type=task_type,
        classes=classes,
        model_checksum=checksum,
        dataset_checksum=dataset_manifest_checksum,
        metrics_snapshot=snapshot,
        policy_version=POLICY_VERSION,
    )
    return ReleasePolicyResult(
        eligible=not reasons,
        reasons=tuple(reasons),
        metrics_snapshot=snapshot,
        inference_contract=contract,
    )
