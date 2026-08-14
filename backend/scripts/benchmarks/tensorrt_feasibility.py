"""Evidence and comparison gates for TASK 3.8 TensorRT feasibility."""

from __future__ import annotations

from typing import Any


def extract_inference_dominance(report: dict[str, Any]) -> dict[str, Any]:
    if "video_analysis" in report:
        clip = report["video_analysis"].get("representative_clip_fixture", {})
        run = clip.get("runs", {}).get("baseline", {})
        stages = run.get("stages_seconds", {})
        mode = str(clip.get("mode", "unknown"))
    else:
        stages = report.get("stages_seconds", {})
        mode = str(report.get("mode", "unknown"))
    total = float(stages.get("total") or 0.0)
    inference = float(stages.get("inference") or 0.0)
    return {
        "mode": mode,
        "inference_seconds": inference,
        "total_seconds": total,
        "inference_fraction": inference / total if total > 0 else None,
    }


def evaluate_prerequisites(
    performance_report: dict[str, Any],
    precision_report: dict[str, Any],
    *,
    minimum_inference_fraction: float,
) -> dict[str, Any]:
    dominance = extract_inference_dominance(performance_report)
    reasons: list[str] = []
    if dominance["mode"] != "live":
        reasons.append("Dominant-stage evidence is fixture-only, not a live target-worker run.")
    fraction = dominance["inference_fraction"]
    if fraction is None or fraction < minimum_inference_fraction:
        reasons.append("Inference is not proven to be the dominant end-to-end stage.")
    if precision_report.get("mode") != "live":
        reasons.append("FP16 accuracy/performance evidence is not from a live CUDA worker.")
    precision_analysis = precision_report.get("analysis", {})
    if not precision_analysis.get("accuracy_complete"):
        reasons.append("FP16 validation accuracy evidence is incomplete.")
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "dominance": dominance,
        "precision_mode": precision_report.get("mode", "unknown"),
        "minimum_inference_fraction": minimum_inference_fraction,
    }


def analyze_runtime_comparison(
    rows: list[dict[str, Any]],
    *,
    mode: str,
    minimum_throughput_improvement_percent: float,
    max_map50_regression: float,
    max_recall_regression: float,
) -> dict[str, Any]:
    by_runtime = {str(row.get("runtime")): row for row in rows}
    pytorch = by_runtime.get("pytorch_fp16")
    engine = by_runtime.get("tensorrt_fp16")
    if pytorch is None or engine is None:
        return {"adopt_tensorrt": False, "reason": "Both runtime rows are required."}
    baseline_ips = float(pytorch.get("images_per_second") or 0.0)
    engine_ips = float(engine.get("images_per_second") or 0.0)
    throughput_delta = ((engine_ips / baseline_ips) - 1.0) * 100.0 if baseline_ips > 0 else None
    map50_regression = float(pytorch.get("map50") or 0.0) - float(engine.get("map50") or 0.0)
    recall_regression = float(pytorch.get("recall") or 0.0) - float(engine.get("recall") or 0.0)
    numeric_gates_pass = bool(
        engine.get("stable")
        and throughput_delta is not None
        and throughput_delta >= minimum_throughput_improvement_percent
        and map50_regression <= max_map50_regression
        and recall_regression <= max_recall_regression
    )
    adopt = mode == "live" and numeric_gates_pass
    return {
        "adopt_tensorrt": adopt,
        "numeric_gates_pass": numeric_gates_pass,
        "throughput_improvement_percent": throughput_delta,
        "map50_regression": map50_regression,
        "recall_regression": recall_regression,
        "cold_start_delta_ms": float(engine.get("cold_start_ms") or 0.0)
        - float(pytorch.get("cold_start_ms") or 0.0),
        "reason": (
            "TensorRT passed the registered live feasibility gates."
            if adopt
            else "TensorRT is not approved for the production runtime."
        ),
    }


def operational_comparison() -> list[dict[str, str]]:
    return [
        {
            "criterion": "deployment_complexity",
            "pytorch": "Existing pinned worker image and portable .pt artifact.",
            "tensorrt": "Adds TensorRT/CUDA compatibility and engine build operations.",
        },
        {
            "criterion": "model_management_burden",
            "pytorch": "One checksum-addressed production artifact.",
            "tensorrt": "Engine artifact must be tied to model, precision, batch, GPU, and runtime versions.",
        },
        {
            "criterion": "rollback",
            "pytorch": "Current supported path.",
            "tensorrt": "Keep PyTorch authoritative; an engine can only be an optional derivative.",
        },
    ]
