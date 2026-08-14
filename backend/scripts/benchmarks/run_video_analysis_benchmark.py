#!/usr/bin/env python3
"""PERF-001/002 video-analysis benchmark harness.

Loads a versioned manifest, optionally runs in --fixture mode (no GPU), and
emits a machine-readable JSON report with baseline vs experiment comparison and
parity check stubs for frames/classes/counts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SUPPORTED_MANIFEST_VERSION = 1


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("version", -1)) != SUPPORTED_MANIFEST_VERSION:
        raise SystemExit(f"Unsupported manifest version: {payload.get('version')!r}")
    for key in (
        "name",
        "model_hash",
        "hardware",
        "frame_stride_seconds",
        "confidence_threshold",
        "expected_stage_keys",
        "parity_tolerances",
    ):
        if key not in payload:
            raise SystemExit(f"Manifest missing required key: {key}")
    return payload


def _stage_report(
    *,
    label: str,
    timings: dict[str, float],
    expected_keys: list[str],
    extra: dict[str, Any],
) -> dict[str, Any]:
    stages = {key: float(timings.get(key, 0.0)) for key in expected_keys}
    return {
        "label": label,
        "stages_seconds": stages,
        "missing_stages": [key for key in expected_keys if key not in timings],
        "frames_per_second": float(extra.get("frames_per_second", 0.0)),
        "inference_batch_throughput": float(extra.get("inference_batch_throughput", 0.0)),
        "detection_count": int(extra.get("detection_count", 0)),
        "peak_memory_mb": extra.get("peak_memory_mb"),
        "selected_frames": list(extra.get("selected_frames", [])),
        "classes": list(extra.get("classes", [])),
        "class_counts": dict(extra.get("class_counts", {})),
        "detections": list(extra.get("detections", [])),
    }


def build_fixture_run(
    manifest: dict[str, Any],
    *,
    baseline_label: str,
    experiment_label: str,
) -> dict[str, Any]:
    fixture = manifest.get("fixture") or {}
    baseline_raw = dict(fixture.get("baseline") or {})
    experiment_raw = dict(fixture.get("experiment") or {})
    expected = list(manifest["expected_stage_keys"])
    baseline = _stage_report(
        label=baseline_label,
        timings=dict(baseline_raw.get("stage_timings_seconds") or {}),
        expected_keys=expected,
        extra=baseline_raw,
    )
    experiment = _stage_report(
        label=experiment_label,
        timings=dict(experiment_raw.get("stage_timings_seconds") or {}),
        expected_keys=expected,
        extra=experiment_raw,
    )
    return {"baseline": baseline, "experiment": experiment}


def compare_runs(baseline: dict[str, Any], experiment: dict[str, Any]) -> dict[str, Any]:
    base_total = float(baseline["stages_seconds"].get("total", 0.0))
    exp_total = float(experiment["stages_seconds"].get("total", 0.0))
    delta = base_total - exp_total
    improvement_pct = (delta / base_total * 100.0) if base_total > 0 else 0.0
    stage_deltas = {
        key: float(baseline["stages_seconds"].get(key, 0.0))
        - float(experiment["stages_seconds"].get(key, 0.0))
        for key in sorted(
            set(baseline["stages_seconds"]) | set(experiment["stages_seconds"])
        )
    }
    return {
        "total_seconds_baseline": base_total,
        "total_seconds_experiment": exp_total,
        "total_seconds_delta": delta,
        "improvement_percent": round(improvement_pct, 3),
        "stage_seconds_delta": stage_deltas,
        "detection_count_delta": int(experiment["detection_count"])
        - int(baseline["detection_count"]),
        "frames_per_second_delta": float(experiment["frames_per_second"])
        - float(baseline["frames_per_second"]),
    }


def _detections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("detections")
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _confidence_parity(
    baseline: dict[str, Any],
    experiment: dict[str, Any],
    tolerance: float,
) -> dict[str, Any]:
    left = _detections(baseline)
    right = _detections(experiment)
    if not left and not right:
        return {
            "passed": True,
            "required": True,
            "compared": 0,
            "tolerance": tolerance,
            "note": "no per-detection confidence samples provided",
        }
    if len(left) != len(right):
        return {
            "passed": False,
            "required": True,
            "compared": 0,
            "tolerance": tolerance,
            "note": "detection list lengths differ",
        }
    max_delta = 0.0
    for index, (base, exp) in enumerate(zip(left, right, strict=True)):
        try:
            delta = abs(float(base["confidence"]) - float(exp["confidence"]))
        except (KeyError, TypeError, ValueError):
            return {
                "passed": False,
                "required": True,
                "compared": index,
                "tolerance": tolerance,
                "note": "missing or invalid confidence",
            }
        max_delta = max(max_delta, delta)
        if delta > tolerance:
            return {
                "passed": False,
                "required": True,
                "compared": index + 1,
                "max_delta": max_delta,
                "tolerance": tolerance,
            }
    return {
        "passed": True,
        "required": True,
        "compared": len(left),
        "max_delta": max_delta,
        "tolerance": tolerance,
    }


def _box_parity(
    baseline: dict[str, Any],
    experiment: dict[str, Any],
    tolerance: float,
) -> dict[str, Any]:
    left = _detections(baseline)
    right = _detections(experiment)
    if not left and not right:
        return {
            "passed": True,
            "required": True,
            "compared": 0,
            "tolerance": tolerance,
            "note": "no per-detection boxes provided",
        }
    if len(left) != len(right):
        return {
            "passed": False,
            "required": True,
            "compared": 0,
            "tolerance": tolerance,
            "note": "detection list lengths differ",
        }
    max_delta = 0.0
    for index, (base, exp) in enumerate(zip(left, right, strict=True)):
        try:
            box_l = [float(base[key]) for key in ("x1", "y1", "x2", "y2")]
            box_r = [float(exp[key]) for key in ("x1", "y1", "x2", "y2")]
        except (KeyError, TypeError, ValueError):
            return {
                "passed": False,
                "required": True,
                "compared": index,
                "tolerance": tolerance,
                "note": "missing or invalid box",
            }
        delta = max(abs(a - b) for a, b in zip(box_l, box_r, strict=True))
        max_delta = max(max_delta, delta)
        if delta > tolerance:
            return {
                "passed": False,
                "required": True,
                "compared": index + 1,
                "max_delta": max_delta,
                "tolerance": tolerance,
            }
    return {
        "passed": True,
        "required": True,
        "compared": len(left),
        "max_delta": max_delta,
        "tolerance": tolerance,
    }


def parity_check(
    baseline: dict[str, Any],
    experiment: dict[str, Any],
    tolerances: dict[str, Any],
) -> dict[str, Any]:
    """Parity gates for frames/classes/counts and per-detection confidence/boxes."""
    frames_ok = list(baseline.get("selected_frames") or []) == list(
        experiment.get("selected_frames") or []
    )
    classes_ok = sorted(baseline.get("classes") or []) == sorted(
        experiment.get("classes") or []
    )
    counts_ok = int(baseline.get("detection_count") or 0) == int(
        experiment.get("detection_count") or 0
    )
    class_counts_ok = dict(baseline.get("class_counts") or {}) == dict(
        experiment.get("class_counts") or {}
    )
    require_frames = bool(tolerances.get("frames_must_match", True))
    require_classes = bool(tolerances.get("classes_must_match", True))
    require_counts = bool(tolerances.get("detection_count_must_match", True))
    confidence_tol = float(tolerances.get("confidence", 1e-5))
    box_tol = float(tolerances.get("box", 1e-5))
    checks = {
        "frames": {"passed": frames_ok, "required": require_frames},
        "classes": {"passed": classes_ok, "required": require_classes},
        "detection_count": {"passed": counts_ok, "required": require_counts},
        "class_counts": {"passed": class_counts_ok, "required": require_counts},
        "confidence_tolerance": _confidence_parity(baseline, experiment, confidence_tol),
        "box_tolerance": _box_parity(baseline, experiment, box_tol),
    }
    failed_required = [
        name
        for name, result in checks.items()
        if result.get("required") and not result.get("passed")
    ]
    return {
        "passed": not failed_required,
        "failed_required": failed_required,
        "checks": checks,
    }


def build_report(
    *,
    manifest: dict[str, Any],
    mode: str,
    baseline_label: str,
    experiment_label: str,
    runs: dict[str, Any],
) -> dict[str, Any]:
    baseline = runs["baseline"]
    experiment = runs["experiment"]
    comparison = compare_runs(baseline, experiment)
    parity = parity_check(baseline, experiment, dict(manifest["parity_tolerances"]))
    return {
        "version": 1,
        "mode": mode,
        "manifest": {
            "name": manifest["name"],
            "model_name": manifest.get("model_name"),
            "model_hash": manifest["model_hash"],
            "hardware": manifest["hardware"],
            "frame_stride_seconds": manifest["frame_stride_seconds"],
            "confidence_threshold": manifest["confidence_threshold"],
            "sahi_enabled": bool(manifest.get("sahi_enabled", False)),
            "tracking_enabled": bool(manifest.get("tracking_enabled", False)),
        },
        "labels": {
            "baseline": baseline_label,
            "experiment": experiment_label,
        },
        "runs": {
            "baseline": baseline,
            "experiment": experiment,
        },
        "comparison": comparison,
        "parity": parity,
        "gates": {
            "optimization_defaults_remain_off": True,
            "note": (
                "Do not enable VIDEO_ANALYSIS_DECODE_STRIDE_ENABLED, "
                "VIDEO_ANALYSIS_INFERENCE_BATCH_SIZE>1, or related gates until a "
                "measured GO is recorded in docs/perf-002-experiment-gates.md."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        type=Path,
        nargs="?",
        default=Path(__file__).with_name("video_analysis_manifest.example.json"),
        help="Path to benchmark manifest JSON",
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Use synthetic timings/detection counts from the manifest (no GPU).",
    )
    parser.add_argument("--baseline-label", default="baseline")
    parser.add_argument("--experiment-label", default="experiment")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the JSON report (also printed to stdout).",
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    if not args.fixture:
        print(
            "Live GPU/video runs are not wired in this harness yet; use --fixture "
            "for machine-readable offline reports.",
            file=sys.stderr,
        )
        return 2

    runs = build_fixture_run(
        manifest,
        baseline_label=args.baseline_label,
        experiment_label=args.experiment_label,
    )
    report = build_report(
        manifest=manifest,
        mode="fixture",
        baseline_label=args.baseline_label,
        experiment_label=args.experiment_label,
        runs=runs,
    )
    text = json.dumps(report, sort_keys=True, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["parity"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
