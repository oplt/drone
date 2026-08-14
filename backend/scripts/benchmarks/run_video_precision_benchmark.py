#!/usr/bin/env python3
"""TASK 3.7 FP32/FP16 accuracy and throughput benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCHMARKS_DIR = Path(__file__).resolve().parent
for path in (str(REPO_ROOT), str(BENCHMARKS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from inference_batch_benchmark import generate_synthetic_images  # noqa: E402
from precision_benchmark import (  # noqa: E402
    analyze_precision_rows,
    build_fixture_rows,
    metric_value,
)

from backend.modules.video_analysis.model_storage import ensure_model_file  # noqa: E402
from backend.modules.video_analysis.service.inference_profile_runtime import (  # noqa: E402
    precision_predict_options,
    resolve_precision_mode,
)

SUPPORTED_MANIFEST_VERSION = 1
DEFAULT_MANIFEST = Path(__file__).with_name("video_precision_manifest.example.json")
DEFAULT_OUTPUT = REPO_ROOT / "docs/benchmarks/video-precision-report.json"
DEFAULT_MARKDOWN = REPO_ROOT / "docs/benchmarks/video-precision-benchmark.md"


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("version", -1)) != SUPPORTED_MANIFEST_VERSION:
        raise SystemExit(f"Unsupported manifest version: {payload.get('version')!r}")
    for key in ("name", "model_name", "gates"):
        if key not in payload:
            raise SystemExit(f"Manifest missing required key: {key}")
    return payload


def _synchronize_cuda() -> None:
    import torch

    if torch.cuda.is_available():
        torch.cuda.synchronize()


def _benchmark_throughput(
    model: Any,
    images: list[Any],
    *,
    precision_mode: str,
    manifest: dict[str, Any],
) -> tuple[float, float]:
    options = precision_predict_options(precision_mode)
    predict_options = {
        "source": images,
        "conf": float(manifest.get("confidence_threshold", 0.35)),
        "imgsz": int(manifest.get("image_size", 640)),
        "device": str(manifest.get("device", "cuda:0")),
        "verbose": False,
        **options,
    }
    for _ in range(int(manifest.get("warmup_batches", 2))):
        model.predict(**predict_options)
    _synchronize_cuda()
    timed_batches = int(manifest.get("timed_batches", 10))
    started = time.monotonic()
    for _ in range(timed_batches):
        model.predict(**predict_options)
    _synchronize_cuda()
    elapsed = time.monotonic() - started
    total_images = len(images) * timed_batches
    return total_images / elapsed, elapsed * 1000.0 / timed_batches


def _validation_metrics(
    model: Any,
    *,
    precision_mode: str,
    manifest: dict[str, Any],
) -> tuple[float | None, float | None]:
    data = manifest.get("validation_data")
    if not data:
        raise SystemExit("Live precision benchmark requires validation_data")
    result = model.val(
        data=str(data),
        imgsz=int(manifest.get("image_size", 640)),
        batch=int(manifest.get("batch_size", 1)),
        device=str(manifest.get("device", "cuda:0")),
        verbose=False,
        **precision_predict_options(precision_mode),
    )
    metrics = dict(getattr(result, "results_dict", {}) or {})
    return (
        metric_value(metrics, "metrics/mAP50(B)", "metrics/mAP50"),
        metric_value(metrics, "metrics/recall(B)", "metrics/recall"),
    )


def run_live_rows(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    device = str(manifest.get("device", "cuda:0"))
    resolve_precision_mode("fp16", device=device)
    from ultralytics import YOLO

    weights = ensure_model_file(str(manifest["model_name"]))
    digest = hashlib.sha256(weights.read_bytes()).hexdigest()
    batch_size = int(manifest.get("batch_size", 1))
    images = generate_synthetic_images(
        batch_size,
        width=int(manifest.get("source_width", 1920)),
        height=int(manifest.get("source_height", 1080)),
        seed=7,
    )
    rows: list[dict[str, Any]] = []
    for precision_mode in ("fp32", "fp16"):
        model = YOLO(str(weights))
        map50, recall = _validation_metrics(model, precision_mode=precision_mode, manifest=manifest)
        images_per_second, batch_latency_ms = _benchmark_throughput(
            model, images, precision_mode=precision_mode, manifest=manifest
        )
        rows.append(
            {
                "precision_mode": precision_mode,
                "supported": True,
                "stable": True,
                "map50": map50,
                "recall": recall,
                "images_per_second": images_per_second,
                "batch_latency_ms": batch_latency_ms,
            }
        )
    return rows, digest


def build_report(
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    mode: str,
    model_checksum: str,
) -> dict[str, Any]:
    gates = manifest["gates"]
    analysis = analyze_precision_rows(
        rows,
        mode=mode,
        min_throughput_improvement_percent=float(gates["min_throughput_improvement_percent"]),
        max_map50_regression=float(gates["max_map50_regression"]),
        max_recall_regression=float(gates["max_recall_regression"]),
    )
    return {
        "version": 1,
        "mode": mode,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "manifest": {key: value for key, value in manifest.items() if key != "fixture_rows"},
        "model_checksum": model_checksum,
        "rows": rows,
        "analysis": analysis,
        "production_default": "fp32",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Video inference precision benchmark",
        "",
        "TASK 3.7 compares FP32 and opt-in FP16 accuracy and throughput.",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Model checksum: `{report['model_checksum']}`",
        f"- Production default: `{report['production_default']}`",
        "",
        "| precision | img/s | batch ms | mAP50 | recall | supported | stable |",
        "|---|---:|---:|---:|---:|:---:|:---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| {precision} | {ips:.2f} | {latency:.2f} | {map50:.4f} | "
            "{recall:.4f} | {supported} | {stable} |".format(
                precision=row["precision_mode"],
                ips=float(row.get("images_per_second") or 0.0),
                latency=float(row.get("batch_latency_ms") or 0.0),
                map50=float(row.get("map50") or 0.0),
                recall=float(row.get("recall") or 0.0),
                supported="yes" if row.get("supported") else "no",
                stable="yes" if row.get("stable") else "no",
            )
        )
    analysis = report["analysis"]
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Promote FP16: **{'yes' if analysis['promote_fp16'] else 'no'}**",
            f"- Reason: {analysis['reason']}",
            "",
            "Fixture measurements are synthetic and cannot change production defaults.",
            "Run live on the target CUDA worker with an audited validation dataset.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--fixture", action="store_true")
    args = parser.parse_args(argv)
    manifest = load_manifest(args.manifest)
    if args.fixture:
        rows = build_fixture_rows(manifest)
        checksum = str(manifest.get("fixture_model_checksum", "fixture"))
        mode = "fixture"
    else:
        rows, checksum = run_live_rows(manifest)
        mode = "live"
    report = build_report(manifest, rows, mode=mode, model_checksum=checksum)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(render_markdown(report))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
