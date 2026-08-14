from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_benchmark_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "benchmarks"
        / "run_vision_training_dataloader_benchmark.py"
    )
    spec = importlib.util.spec_from_file_location(
        "vision_training_dataloader_benchmark",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_analyze_adoption_prefers_smallest_workers_meeting_threshold() -> None:
    mod = _load_benchmark_module()
    runs = {
        "0": {
            "epoch_duration_seconds": 42.5,
            "gpu_util_avg_pct": 62.0,
            "stable": True,
        },
        "2": {
            "epoch_duration_seconds": 36.1,
            "gpu_util_avg_pct": 74.0,
            "stable": True,
        },
        "4": {
            "epoch_duration_seconds": 35.4,
            "gpu_util_avg_pct": 76.0,
            "stable": True,
        },
    }
    adoption = mod.analyze_adoption(runs, threshold_percent=15.0)
    assert adoption["recommended_workers"] == 2
    assert adoption["recommend_default_change"] is True
    assert adoption["best_workers"] == 4


def test_analyze_adoption_keeps_default_when_below_threshold() -> None:
    mod = _load_benchmark_module()
    runs = {
        "0": {"epoch_duration_seconds": 40.0, "stable": True},
        "2": {"epoch_duration_seconds": 38.0, "stable": True},
    }
    adoption = mod.analyze_adoption(runs, threshold_percent=15.0)
    assert adoption["recommended_workers"] == 0
    assert adoption["recommend_default_change"] is False


def test_build_fixture_runs_requires_manifest_rows() -> None:
    mod = _load_benchmark_module()
    manifest = {
        "worker_counts": [0, 2],
        "fixture": {
            "0": {"epoch_duration_seconds": 1.0, "stable": True},
            "2": {"epoch_duration_seconds": 0.8, "stable": True},
        },
    }
    runs = mod.build_fixture_runs(manifest)
    assert runs["0"]["workers"] == 0
    assert runs["2"]["mode"] == "fixture"
