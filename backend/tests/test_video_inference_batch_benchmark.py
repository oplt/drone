from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    REPO_ROOT
    / "backend/scripts/benchmarks/video_inference_batch_manifest.example.json"
)
RUNNER = REPO_ROOT / "backend/scripts/benchmarks/run_video_inference_batch_benchmark.py"
CORE = REPO_ROOT / "backend/scripts/benchmarks/inference_batch_benchmark.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def manifest() -> dict:
    runner = _load_module(RUNNER, "run_video_inference_batch_benchmark")
    return runner.load_manifest(MANIFEST)


def test_fixture_manifest_builds_report_rows(manifest: dict) -> None:
    runner = _load_module(RUNNER, "run_video_inference_batch_benchmark_fixture")
    core = _load_module(CORE, "inference_batch_benchmark_fixture")

    rows = core.build_fixture_rows(manifest)
    expected = (
        len(manifest["fixture_device_classes"])
        * len(manifest["profiles"])
        * len(manifest["batch_sizes"])
    )
    assert len(rows) == expected
    report = runner.build_report(manifest, rows, mode="fixture")
    assert report["gates"]["opt_in_env"] == "VIDEO_ANALYSIS_INFERENCE_BATCH_SIZE"
    assert report["analysis"]["recommendations"]
    cuda_1080 = next(
        rec
        for rec in report["analysis"]["recommendations"]
        if rec["device_class"] == "cuda" and rec["profile_id"] == "standard_1080p"
    )
    assert cuda_1080["recommended_batch_size"] == 2
    cpu_1080 = next(
        rec
        for rec in report["analysis"]["recommendations"]
        if rec["device_class"] == "cpu" and rec["profile_id"] == "standard_1080p"
    )
    assert cpu_1080["recommended_batch_size"] == 1
    markdown = runner.render_markdown(report)
    assert "Recommended defaults by device class / profile" in markdown


def test_analyze_recommendations_skips_oom_batches() -> None:
    core = _load_module(CORE, "inference_batch_benchmark_analyze")
    rows = [
        {
            "device_class": "cuda",
            "profile_id": "standard_4k",
            "profile_label": "4K",
            "batch_size": 1,
            "images_per_second": 10.0,
            "gpu_util_avg_pct": 60.0,
            "stable": True,
            "oom": False,
        },
        {
            "device_class": "cuda",
            "profile_id": "standard_4k",
            "profile_label": "4K",
            "batch_size": 16,
            "images_per_second": 0.0,
            "gpu_util_avg_pct": None,
            "stable": False,
            "oom": True,
        },
    ]
    analysis = core.analyze_recommendations(rows, throughput_threshold_percent=20.0)
    rec = analysis["recommendations"][0]
    assert rec["recommended_batch_size"] == 1
    assert any(row.get("oom") for row in analysis["comparisons"])


def test_generate_synthetic_images_shape() -> None:
    core = _load_module(CORE, "inference_batch_benchmark_images")
    images = core.generate_synthetic_images(3, width=640, height=480, seed=1)
    assert len(images) == 3
    assert images[0].shape == (480, 640, 3)
    assert images[0].dtype == np.uint8


def test_runner_fixture_subprocess(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--fixture",
            "--manifest",
            str(MANIFEST),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["mode"] == "fixture"
    assert len(report["rows"]) > 0
