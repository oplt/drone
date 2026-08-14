#!/usr/bin/env python3
"""TASK 3.4 repeatable YOLO inference batch-size benchmark harness.

Finds practical ``predict_batch`` sizes per device class and inference profile
without hard-coding one universal ``VIDEO_ANALYSIS_INFERENCE_BATCH_SIZE``.
"""

from __future__ import annotations

import argparse
import csv
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

from inference_batch_benchmark import (  # noqa: E402
    analyze_recommendations,
    batch_key,
    benchmark_batch_size_live,
    build_fixture_rows,
    detect_device_class,
    generate_synthetic_images,
    resolve_device_label,
    row_from_result,
)

SUPPORTED_MANIFEST_VERSION = 1
DEFAULT_MANIFEST = Path(__file__).with_name(
    "video_inference_batch_manifest.example.json"
)
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "benchmarks" / "video-inference-batch-report.json"
DEFAULT_MARKDOWN = REPO_ROOT / "docs" / "benchmarks" / "video-inference-batch-benchmark.md"


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("version", -1)) != SUPPORTED_MANIFEST_VERSION:
        raise SystemExit(f"Unsupported manifest version: {payload.get('version')!r}")
    for key in ("name", "model_name", "profiles", "batch_sizes"):
        if key not in payload:
            raise SystemExit(f"Manifest missing required key: {key}")
    return payload


def run_live_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        import torch
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit(
            "Live benchmark requires torch and ultralytics in the active environment."
        ) from exc

    from backend.modules.video_analysis.model_storage import ensure_model_file

    device_class = detect_device_class()
    device = resolve_device_label(device_class)
    weights = ensure_model_file(manifest["model_name"])
    model = YOLO(str(weights))
    confidence = float(manifest.get("confidence_threshold", 0.35))
    warmup_batches = int(manifest.get("warmup_batches", 2))
    timed_batches = int(manifest.get("timed_batches", 10))
    max_batch = max(int(size) for size in manifest["batch_sizes"])
    rows: list[dict[str, Any]] = []

    for profile in manifest["profiles"]:
        width = int(profile.get("width", 1920))
        height = int(profile.get("height", 1080))
        images = generate_synthetic_images(max_batch, width=width, height=height)
        for batch_size in manifest["batch_sizes"]:
            batch_size = int(batch_size)
            if batch_size > max_batch:
                continue
            result = benchmark_batch_size_live(
                model=model,
                images=images,
                batch_size=batch_size,
                device=device,
                confidence_threshold=confidence,
                warmup_batches=warmup_batches,
                timed_batches=timed_batches,
            )
            if result.oom and device_class == "cuda":
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass
            rows.append(
                row_from_result(
                    device_class=device_class,
                    profile=profile,
                    batch_size=batch_size,
                    result=result,
                )
            )
            if result.oom:
                break
    return rows


def build_report(
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    mode: str,
) -> dict[str, Any]:
    threshold = float(manifest.get("adoption_throughput_threshold_percent", 20.0))
    analysis = analyze_recommendations(
        rows,
        throughput_threshold_percent=threshold,
    )
    return {
        "version": 1,
        "mode": mode,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "manifest": {
            "name": manifest["name"],
            "model_name": manifest["model_name"],
            "confidence_threshold": manifest.get("confidence_threshold", 0.35),
            "profiles": manifest["profiles"],
            "batch_sizes": manifest["batch_sizes"],
            "warmup_batches": manifest.get("warmup_batches", 2),
            "timed_batches": manifest.get("timed_batches", 10),
            "hardware": manifest.get("hardware"),
        },
        "timing_methodology": {
            "images_per_second": "total_images / wall_seconds during timed_batches loop",
            "batch_latency_ms": "mean wall time per predict() batch call",
            "per_image_latency_ms": "batch_latency_ms / batch_size",
            "gpu_util_avg_pct": "nvidia-smi utilization sampled every 0.5s",
            "vram_peak_mb": "max(nvidia-smi memory.used, torch.cuda.max_memory_allocated)",
            "ram_peak_mb": "psutil virtual_memory used peak during timed loop",
        },
        "rows": rows,
        "analysis": analysis,
        "gates": {
            "production_default": analysis["production_default_batch_size"],
            "opt_in_env": "VIDEO_ANALYSIS_INFERENCE_BATCH_SIZE",
            "change_default_only_after_live_benchmark": True,
        },
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "device_class",
        "profile_id",
        "profile_label",
        "width",
        "height",
        "imgsz",
        "batch_size",
        "images_per_second",
        "batch_latency_ms",
        "per_image_latency_ms",
        "gpu_util_avg_pct",
        "vram_peak_mb",
        "ram_peak_mb",
        "stable",
        "oom",
        "available",
        "error",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def render_markdown(report: dict[str, Any]) -> str:
    analysis = report["analysis"]
    lines = [
        "# Video inference batch-size benchmark",
        "",
        "Repeatable harness for TASK 3.4. Compares standard Ultralytics YOLO",
        "``predict_batch`` throughput by device class and inference profile.",
        "",
        "## Runbook",
        "",
        "Fixture (no GPU):",
        "",
        "```sh",
        "python3 backend/scripts/benchmarks/run_video_inference_batch_benchmark.py \\",
        "  --fixture --output docs/benchmarks/video-inference-batch-report.json",
        "python3 backend/scripts/benchmarks/run_video_inference_batch_benchmark.py \\",
        "  --render-markdown docs/benchmarks/video-inference-batch-report.json \\",
        "  --markdown-output docs/benchmarks/video-inference-batch-benchmark.md",
        "```",
        "",
        "Live (torch + ultralytics + optional NVIDIA GPU):",
        "",
        "```sh",
        "python3 backend/scripts/benchmarks/run_video_inference_batch_benchmark.py \\",
        "  --output /tmp/video-inference-batch-report.json",
        "```",
        "",
        "## Timing methodology",
        "",
        "| Metric | Definition |",
        "|--------|------------|",
        "| images_per_second | total images / wall seconds in timed loop |",
        "| batch_latency_ms | mean wall time per ``predict()`` batch |",
        "| per_image_latency_ms | batch latency / batch size |",
        "| gpu_util_avg_pct | ``nvidia-smi`` GPU utilization sampled every 0.5s |",
        "| vram_peak_mb | peak VRAM from ``nvidia-smi`` and ``torch.cuda.max_memory_allocated`` |",
        "",
        f"- Report mode: `{report['mode']}`",
        f"- Manifest: `{report['manifest']['name']}`",
        f"- Model: `{report['manifest']['model_name']}`",
        "",
        "## Results",
        "",
        "| device | profile | batch | img/s | batch ms | img ms | GPU % | VRAM MiB | stable | OOM |",
        "|--------|---------|------:|------:|---------:|-------:|------:|---------:|:------:|:---:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| {device} | {profile} | {batch} | {ips:.1f} | {batch_ms:.1f} | {img_ms:.2f} | {gpu} | {vram} | {stable} | {oom} |".format(
                device=row["device_class"],
                profile=row["profile_id"],
                batch=row["batch_size"],
                ips=float(row.get("images_per_second") or 0.0),
                batch_ms=float(row.get("batch_latency_ms") or 0.0),
                img_ms=float(row.get("per_image_latency_ms") or 0.0),
                gpu=(
                    f"{float(row['gpu_util_avg_pct']):.0f}"
                    if row.get("gpu_util_avg_pct") is not None
                    else "n/a"
                ),
                vram=(
                    f"{float(row['vram_peak_mb']):.0f}"
                    if row.get("vram_peak_mb") is not None
                    else "n/a"
                ),
                stable="yes" if row.get("stable", True) else "no",
                oom="yes" if row.get("oom") else "no",
            )
        )
    if report["mode"] == "fixture":
        lines.extend(
            [
                "",
                "> Fixture timings are synthetic placeholders. Replace by running live",
                "> commands on representative CPU and CUDA hosts.",
                "",
            ]
        )
    lines.extend(
        [
            "## Recommended defaults by device class / profile",
            "",
            "| device | profile | recommended batch | env override? | notes |",
            "|--------|---------|------------------:|:-------------:|-------|",
        ]
    )
    for rec in analysis.get("recommendations", []):
        lines.append(
            "| {device} | {profile} | {batch} | {override} | {reason} |".format(
                device=rec["device_class"],
                profile=rec["profile_id"],
                batch=rec["recommended_batch_size"],
                override="yes" if rec.get("recommend_env_override") else "no",
                reason=rec.get("reason", ""),
            )
        )
    lines.extend(
        [
            "",
            f"- Throughput threshold: `{analysis.get('throughput_threshold_percent')}%`",
            f"- Production default: `{analysis.get('production_default_batch_size')}`",
            f"- Change code default only after live benchmark: **{'yes' if analysis.get('change_default_only_after_live_benchmark') else 'no'}**",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Benchmark manifest JSON",
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Use synthetic timings from manifest fixture (no GPU).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON report output path",
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        help="Optional CSV flatten output path",
    )
    parser.add_argument(
        "--render-markdown",
        type=Path,
        help="Render markdown from an existing JSON report path.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=DEFAULT_MARKDOWN,
        help="Markdown output path when rendering a report.",
    )
    args = parser.parse_args()

    if args.render_markdown:
        report = json.loads(args.render_markdown.read_text(encoding="utf-8"))
        markdown = render_markdown(report)
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown + "\n", encoding="utf-8")
        print(json.dumps({"markdown_output": str(args.markdown_output)}, indent=2))
        return 0

    manifest = load_manifest(args.manifest)
    if args.fixture:
        rows = build_fixture_rows(manifest)
        report_mode = "fixture"
    else:
        rows = run_live_rows(manifest)
        report_mode = "live"

    report = build_report(manifest, rows, mode=report_mode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.csv_output:
        write_csv(rows, args.csv_output)
    print(json.dumps({"output": str(args.output), "mode": report_mode, "rows": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
