"""Analysis helpers for the TASK 3.7 FP16 inference benchmark."""

from __future__ import annotations

from typing import Any


def build_fixture_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = manifest.get("fixture_rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Precision benchmark fixture_rows must be a non-empty list")
    return [dict(row) for row in rows]


def _regression(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None:
        return None
    return baseline - candidate


def analyze_precision_rows(
    rows: list[dict[str, Any]],
    *,
    mode: str,
    min_throughput_improvement_percent: float,
    max_map50_regression: float,
    max_recall_regression: float,
) -> dict[str, Any]:
    by_mode = {str(row.get("precision_mode")): row for row in rows}
    baseline = by_mode.get("fp32")
    candidate = by_mode.get("fp16")
    if baseline is None or candidate is None:
        return {
            "promote_fp16": False,
            "reason": "Both fp32 and fp16 rows are required.",
            "live_evidence": mode == "live",
        }

    baseline_ips = float(baseline.get("images_per_second") or 0.0)
    candidate_ips = float(candidate.get("images_per_second") or 0.0)
    throughput_improvement = (
        ((candidate_ips / baseline_ips) - 1.0) * 100.0 if baseline_ips > 0 else None
    )
    map50_regression = _regression(baseline.get("map50"), candidate.get("map50"))
    recall_regression = _regression(baseline.get("recall"), candidate.get("recall"))
    accuracy_complete = map50_regression is not None and recall_regression is not None
    numeric_gates_pass = bool(
        candidate.get("supported")
        and candidate.get("stable")
        and throughput_improvement is not None
        and throughput_improvement >= min_throughput_improvement_percent
        and accuracy_complete
        and map50_regression <= max_map50_regression
        and recall_regression <= max_recall_regression
    )
    live_evidence = mode == "live"
    promote = numeric_gates_pass and live_evidence
    if not live_evidence:
        reason = "Fixture data cannot promote FP16; run on the target CUDA worker."
    elif not accuracy_complete:
        reason = "Validation accuracy metrics are incomplete."
    elif not numeric_gates_pass:
        reason = "FP16 did not satisfy the registered accuracy/performance gates."
    else:
        reason = "FP16 satisfied all gates on the target CUDA worker."
    return {
        "promote_fp16": promote,
        "reason": reason,
        "live_evidence": live_evidence,
        "numeric_gates_pass": numeric_gates_pass,
        "throughput_improvement_percent": throughput_improvement,
        "map50_regression": map50_regression,
        "recall_regression": recall_regression,
        "accuracy_complete": accuracy_complete,
    }


def metric_value(metrics: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None
