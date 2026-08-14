#!/usr/bin/env python3
"""Capture reproducible performance baseline snapshots for Phase 0."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT.parent / "docs" / "benchmarks" / "performance-baseline-record.json"


def _run_json(cmd: list[str]) -> dict[str, Any]:
    completed = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def _video_fixture_report(manifest: Path) -> dict[str, Any]:
    script = BENCHMARKS / "run_video_analysis_benchmark.py"
    return _run_json(
        [
            sys.executable,
            str(script),
            str(manifest),
            "--fixture",
            "--baseline-label",
            "baseline",
            "--experiment-label",
            "baseline",
        ]
    )


def _bundle_report() -> dict[str, Any] | None:
    dist = ROOT.parent / "frontend" / "dist"
    if not dist.exists():
        return None
    script = ROOT.parent / "frontend" / "scripts" / "report_bundle_size.mjs"
    completed = subprocess.run(
        ["node", str(script)],
        cwd=ROOT.parent / "frontend",
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return {"available": False, "error": completed.stderr.strip() or completed.stdout.strip()}
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    total_line = next((line for line in lines if line.startswith("Bundle total:")), None)
    largest = [line for line in lines if line.startswith("- ")]
    return {
        "available": True,
        "total": total_line,
        "largest_chunks": largest[:10],
    }


def build_record(*, include_bundle: bool) -> dict[str, Any]:
    small_manifest = BENCHMARKS / "video_analysis_manifest.small.example.json"
    representative_manifest = BENCHMARKS / "video_analysis_manifest.example.json"
    record: dict[str, Any] = {
        "version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "notes": [
            "Fixture video timings are synthetic until live GPU/video harness is wired.",
            "Replace placeholder API and queue metrics after running against a live stack.",
        ],
        "video_analysis": {
            "small_clip_fixture": _video_fixture_report(small_manifest),
            "representative_clip_fixture": _video_fixture_report(representative_manifest),
        },
        "manual_capture_required": {
            "api_latency": {
                "command_hint": "Use hey or vegeta against /agriculture read endpoints while analysis page is open.",
                "targets": [
                    "GET /agriculture/analysis-runs/{id}",
                    "GET /agriculture/analysis-runs/{id}/findings",
                    "GET /agriculture/analysis-runs/{id}/fusion",
                ],
                "metrics": ["p50_ms", "p95_ms", "requests_per_minute_with_page_open"],
            },
            "gpu_utilization": {
                "command_hint": "nvidia-smi dmon -s u -d 5 during inference/training jobs",
                "metrics": ["inference_gpu_util_avg", "training_gpu_util_avg"],
            },
            "agriculture_queue": {
                "command_hint": "curl -s http://127.0.0.1:9090/api/v1/query?query=agriculture_queue_age_seconds_bucket",
                "metrics": ["queue_wait_p95_seconds", "time_to_first_finding_seconds"],
            },
            "training_epoch_duration": {
                "command_hint": "Record vision training run metadata epoch_duration_seconds from run detail API.",
                "metrics": ["epoch_duration_seconds", "dataloader_workers"],
            },
        },
    }
    if include_bundle:
        record["frontend_bundle"] = _bundle_report()
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path for machine-readable baseline record JSON",
    )
    parser.add_argument(
        "--skip-bundle",
        action="store_true",
        help="Do not attempt frontend bundle size capture.",
    )
    args = parser.parse_args()

    record = build_record(include_bundle=not args.skip_bundle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "captured_at": record["captured_at"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
