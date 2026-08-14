#!/usr/bin/env python3
"""Benchmark Ultralytics vision-training dataloader worker counts."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SUPPORTED_MANIFEST_VERSION = 1
DEFAULT_MANIFEST = Path(__file__).with_name(
    "vision_training_dataloader_manifest.example.json"
)


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("version", -1)) != SUPPORTED_MANIFEST_VERSION:
        raise SystemExit(f"Unsupported manifest version: {payload.get('version')!r}")
    for key in ("name", "base_model", "benchmark_epochs", "worker_counts"):
        if key not in payload:
            raise SystemExit(f"Manifest missing required key: {key}")
    return payload


def _worker_key(workers: int) -> str:
    return str(int(workers))


@dataclass
class ResourceSamples:
    cpu_util_avg_pct: float | None = None
    ram_peak_mb: float | None = None
    gpu_util_avg_pct: float | None = None
    _cpu: list[float] = field(default_factory=list)
    _ram_mb: list[float] = field(default_factory=list)
    _gpu: list[float] = field(default_factory=list)
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _sample_loop(self) -> None:
        import psutil

        while not self._stop.is_set():
            self._cpu.append(float(psutil.cpu_percent(interval=None)))
            self._ram_mb.append(float(psutil.virtual_memory().used) / (1024 * 1024))
            gpu = _query_gpu_utilization_pct()
            if gpu is not None:
                self._gpu.append(gpu)
            time.sleep(1.0)

    def finalize(self) -> None:
        self.cpu_util_avg_pct = (
            statistics.mean(self._cpu) if self._cpu else None
        )
        self.ram_peak_mb = max(self._ram_mb) if self._ram_mb else None
        self.gpu_util_avg_pct = (
            statistics.mean(self._gpu) if self._gpu else None
        )


def _query_gpu_utilization_pct() -> float | None:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        line = completed.stdout.strip().splitlines()[0].strip()
        return float(line)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def analyze_adoption(
    runs: dict[str, dict[str, Any]],
    *,
    baseline_workers: int = 0,
    threshold_percent: float = 15.0,
) -> dict[str, Any]:
    baseline = runs.get(_worker_key(baseline_workers))
    if baseline is None:
        return {
            "recommend_default_change": False,
            "reason": f"Missing baseline workers={baseline_workers}",
        }
    baseline_epoch = float(baseline["epoch_duration_seconds"])
    comparisons: list[dict[str, Any]] = []
    best_workers = baseline_workers
    best_epoch = baseline_epoch
    for workers_key, row in sorted(runs.items(), key=lambda item: int(item[0])):
        epoch = float(row["epoch_duration_seconds"])
        improvement_pct = (
            ((baseline_epoch - epoch) / baseline_epoch) * 100.0
            if baseline_epoch > 0
            else 0.0
        )
        comparisons.append(
            {
                "workers": int(workers_key),
                "epoch_duration_seconds": epoch,
                "improvement_vs_baseline_percent": round(improvement_pct, 2),
                "gpu_util_avg_pct": row.get("gpu_util_avg_pct"),
                "stable": bool(row.get("stable", True)),
            }
        )
        if epoch < best_epoch and bool(row.get("stable", True)):
            best_epoch = epoch
            best_workers = int(workers_key)
    best_improvement = (
        ((baseline_epoch - best_epoch) / baseline_epoch) * 100.0
        if baseline_epoch > 0
        else 0.0
    )
    baseline_gpu = baseline.get("gpu_util_avg_pct")
    recommended_workers = baseline_workers
    recommend = False
    for row in sorted(comparisons, key=lambda item: item["workers"]):
        gpu_ok = (
            row.get("gpu_util_avg_pct") is not None
            and baseline_gpu is not None
            and float(row["gpu_util_avg_pct"]) - float(baseline_gpu) >= 10.0
        )
        if not row.get("stable", True):
            continue
        if row["improvement_vs_baseline_percent"] >= threshold_percent or gpu_ok:
            recommended_workers = int(row["workers"])
            recommend = recommended_workers != baseline_workers
            break
    return {
        "baseline_workers": baseline_workers,
        "best_workers": best_workers,
        "best_improvement_percent": round(best_improvement, 2),
        "threshold_percent": threshold_percent,
        "recommend_default_change": recommend,
        "recommended_workers": recommended_workers if recommend else baseline_workers,
        "comparisons": comparisons,
        "reason": (
            "Smallest worker count meeting adoption threshold on this host"
            if recommend
            else "Keep conservative default workers=0 unless live host confirms threshold"
        ),
    }


def build_fixture_runs(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fixture = dict(manifest.get("fixture") or {})
    runs: dict[str, dict[str, Any]] = {}
    for workers in manifest["worker_counts"]:
        key = _worker_key(workers)
        row = dict(fixture.get(key) or fixture.get(workers) or {})
        if not row:
            raise SystemExit(f"Fixture missing workers={workers}")
        runs[key] = {
            "workers": int(workers),
            "mode": "fixture",
            **row,
        }
    return runs


def write_synthetic_yolo_dataset(
    root: Path,
    *,
    images_per_split: int,
    image_size: int,
) -> Path:
    import cv2
    import numpy as np
    import yaml

    for split in ("train", "val", "test"):
        image_dir = root / "images" / split
        label_dir = root / "labels" / split
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        for index in range(images_per_split):
            image = np.random.default_rng(index).integers(
                0, 255, (image_size, image_size, 3), dtype=np.uint8
            )
            stem = f"{split}_{index:03d}"
            cv2.imwrite(str(image_dir / f"{stem}.jpg"), image)
            (label_dir / f"{stem}.txt").write_text(
                "0 0.5 0.5 0.25 0.25", encoding="utf-8"
            )
    config = {
        "path": str(root.resolve()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": ["object"],
    }
    config_path = root / "data.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def run_live_worker_benchmark(
    manifest: dict[str, Any],
    *,
    workers: int,
    dataset_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    try:
        import torch
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit(
            "Live benchmark requires torch and ultralytics in the active environment."
        ) from exc

    from backend.modules.video_analysis.model_storage import ensure_model_file

    device: str | int = 0 if torch.cuda.is_available() else "cpu"
    device_label = f"cuda:{device}" if isinstance(device, int) else str(device)
    weights = ensure_model_file(manifest["base_model"])
    run_dir = output_root / f"workers_{workers}"
    run_dir.mkdir(parents=True, exist_ok=True)
    sampler = ResourceSamples()
    sampler.start()
    started = time.monotonic()
    stable = True
    error: str | None = None
    try:
        model = YOLO(str(weights))
        model.train(
            data=str(dataset_root / "data.yaml"),
            epochs=int(manifest["benchmark_epochs"]),
            imgsz=int(manifest.get("image_size", 640)),
            batch=int(manifest.get("batch_size", 8)),
            device=device,
            project=str(run_dir.parent),
            name=run_dir.name,
            exist_ok=True,
            pretrained=True,
            workers=int(workers),
            plots=False,
            verbose=False,
            seed=0,
            deterministic=True,
        )
    except Exception as exc:
        stable = False
        error = str(exc)
        raise
    finally:
        sampler.stop()
        sampler.finalize()
        total_duration = time.monotonic() - started

    epochs = max(1, int(manifest["benchmark_epochs"]))
    return {
        "workers": workers,
        "mode": "live",
        "device": device_label,
        "epoch_duration_seconds": round(total_duration / epochs, 3),
        "total_duration_seconds": round(total_duration, 3),
        "gpu_util_avg_pct": sampler.gpu_util_avg_pct,
        "cpu_util_avg_pct": sampler.cpu_util_avg_pct,
        "ram_peak_mb": sampler.ram_peak_mb,
        "stable": stable,
        "error": error,
    }


def build_report(
    manifest: dict[str, Any],
    runs: dict[str, dict[str, Any]],
    *,
    mode: str,
) -> dict[str, Any]:
    threshold = float(manifest.get("adoption_threshold_percent", 15.0))
    adoption = analyze_adoption(runs, threshold_percent=threshold)
    return {
        "version": 1,
        "mode": mode,
        "manifest": {
            "name": manifest["name"],
            "base_model": manifest["base_model"],
            "benchmark_epochs": manifest["benchmark_epochs"],
            "worker_counts": manifest["worker_counts"],
            "hardware": manifest.get("hardware"),
        },
        "runs": runs,
        "adoption": adoption,
        "gates": {
            "production_default_workers": 0,
            "change_default_only_if": (
                "recommended_workers != 0 AND recommend_default_change is true "
                "on target GPU hardware"
            ),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    adoption = report["adoption"]
    lines = [
        "# Vision training dataloader worker benchmark",
        "",
        "Ultralytics `workers` argument for YOLO training. Default remains "
        "`VISION_TRAINING_DATALOADER_WORKERS=0` unless live results on your GPU "
        "host meet the adoption threshold.",
        "",
        "## Runbook",
        "",
        "Fixture (no GPU):",
        "",
        "```sh",
        "python3 backend/scripts/benchmarks/run_vision_training_dataloader_benchmark.py \\",
        "  --fixture --output docs/benchmarks/vision-training-dataloader-report.json",
        "```",
        "",
        "Live (torch + ultralytics + optional NVIDIA GPU):",
        "",
        "```sh",
        "python3 backend/scripts/benchmarks/run_vision_training_dataloader_benchmark.py \\",
        "  --output /tmp/vision-dataloader-report.json",
        "python3 backend/scripts/benchmarks/run_vision_training_dataloader_benchmark.py \\",
        "  --render-markdown /tmp/vision-dataloader-report.json \\",
        "  --markdown-output docs/benchmarks/vision-training-dataloader.md",
        "```",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Manifest: `{report['manifest']['name']}`",
        f"- Model: `{report['manifest']['base_model']}`",
        f"- Benchmark epochs per worker setting: `{report['manifest']['benchmark_epochs']}`",
        "",
        "## Results",
        "",
        "| workers | epoch_s | GPU util avg % | CPU util avg % | RAM peak MiB | stable |",
        "|--------:|--------:|---------------:|---------------:|-------------:|:------:|",
    ]
    for row in adoption["comparisons"]:
        run = report["runs"][str(row["workers"])]
        lines.append(
            "| {workers} | {epoch:.1f} | {gpu} | {cpu} | {ram} | {stable} |".format(
                workers=row["workers"],
                epoch=float(run["epoch_duration_seconds"]),
                gpu=(
                    f"{float(run['gpu_util_avg_pct']):.0f}"
                    if run.get("gpu_util_avg_pct") is not None
                    else "n/a"
                ),
                cpu=(
                    f"{float(run['cpu_util_avg_pct']):.0f}"
                    if run.get("cpu_util_avg_pct") is not None
                    else "n/a"
                ),
                ram=(
                    f"{float(run['ram_peak_mb']) / 1024:.1f}"
                    if run.get("ram_peak_mb") is not None
                    else "n/a"
                ),
                stable="yes" if run.get("stable", True) else "no",
            )
        )
    lines.extend(
        [
            "",
            "## Adoption analysis",
            "",
            f"- Baseline workers: `{adoption['baseline_workers']}`",
            f"- Best workers: `{adoption['best_workers']}`",
            f"- Best improvement vs baseline: `{adoption['best_improvement_percent']}%`",
            f"- Threshold: `{adoption['threshold_percent']}%` epoch-time improvement "
            "or materially higher GPU occupancy",
            f"- Recommend opt-in on GPU training host: "
            f"**{'yes' if adoption['recommend_default_change'] else 'no'}**",
            f"- Suggested env for that host: "
            f"`VISION_TRAINING_DATALOADER_WORKERS={adoption['recommended_workers']}`",
            f"- Code default stays: `0` (set env on vision-training worker only)",
            f"- Notes: {adoption['reason']}",
            "",
            "## Guidance",
            "",
            "- **CPU / macOS / Windows / low RAM**: keep `0`.",
            "- **Linux + NVIDIA GPU**: benchmark locally; if workers `2` saves "
            "~15%+ epoch time with stable runs, set env on the vision-training worker only.",
            "- Workers `4` rarely beats `2` unless CPU and RAM headroom are large.",
            "- Record live JSON alongside this doc after hardware changes.",
            "",
        ]
    )
    if report["mode"] == "fixture":
        lines.extend(
            [
                "> Fixture timings are synthetic placeholders. Replace by running the "
                "live command on the target training host.",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        default=DEFAULT_MANIFEST,
    )
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        help="Optional existing YOLO dataset root containing data.yaml",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("/tmp/vision-dataloader-benchmark"),
    )
    parser.add_argument(
        "--render-markdown",
        type=Path,
        help="Render markdown from an existing JSON report path",
    )
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()

    if args.render_markdown is not None:
        report = json.loads(args.render_markdown.read_text(encoding="utf-8"))
        markdown = render_markdown(report)
        if args.markdown_output is not None:
            args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
            args.markdown_output.write_text(markdown, encoding="utf-8")
        print(markdown)
        return 0

    manifest = load_manifest(args.manifest)
    if args.fixture:
        runs = build_fixture_runs(manifest)
        report = build_report(manifest, runs, mode="fixture")
    else:
        root = Path(__file__).resolve().parents[3]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        dataset_root = args.dataset_dir
        if dataset_root is None:
            dataset_root = args.work_dir / "dataset"
            write_synthetic_yolo_dataset(
                dataset_root,
                images_per_split=int(manifest.get("images_per_split", 16)),
                image_size=int(manifest.get("image_size", 640)),
            )
        runs = {}
        for workers in manifest["worker_counts"]:
            runs[_worker_key(workers)] = run_live_worker_benchmark(
                manifest,
                workers=int(workers),
                dataset_root=dataset_root,
                output_root=args.work_dir / "runs",
            )
        report = build_report(manifest, runs, mode="live")

    text = json.dumps(report, sort_keys=True, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
