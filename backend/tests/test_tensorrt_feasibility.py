from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = REPO_ROOT / "backend/scripts/benchmarks"
CORE = BENCHMARK_DIR / "tensorrt_feasibility.py"
RUNNER = BENCHMARK_DIR / "run_tensorrt_feasibility.py"
MANIFEST = BENCHMARK_DIR / "tensorrt_feasibility_manifest.example.json"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_fixture_evidence_blocks_the_experiment() -> None:
    core = _load(CORE, "tensorrt_feasibility_fixture")
    performance = json.loads(
        (REPO_ROOT / "docs/benchmarks/performance-baseline-record.json").read_text()
    )
    precision = json.loads((REPO_ROOT / "docs/benchmarks/video-precision-report.json").read_text())
    result = core.evaluate_prerequisites(performance, precision, minimum_inference_fraction=0.5)

    assert result["dominance"]["inference_fraction"] > 0.5
    assert result["eligible"] is False
    assert any("fixture-only" in reason for reason in result["reasons"])
    assert any("live CUDA" in reason for reason in result["reasons"])


def test_live_dominant_inference_and_precision_evidence_unlocks_runner() -> None:
    core = _load(CORE, "tensorrt_feasibility_prerequisites")
    result = core.evaluate_prerequisites(
        {
            "mode": "live",
            "stages_seconds": {"inference": 60.0, "total": 100.0},
        },
        {"mode": "live", "analysis": {"accuracy_complete": True}},
        minimum_inference_fraction=0.5,
    )

    assert result["eligible"] is True
    assert result["reasons"] == []


def test_live_runtime_comparison_requires_material_gain_and_accuracy_parity() -> None:
    core = _load(CORE, "tensorrt_feasibility_live")
    rows = [
        {
            "runtime": "pytorch_fp16",
            "stable": True,
            "images_per_second": 50,
            "cold_start_ms": 500,
            "map50": 0.70,
            "recall": 0.72,
        },
        {
            "runtime": "tensorrt_fp16",
            "stable": True,
            "images_per_second": 70,
            "cold_start_ms": 650,
            "map50": 0.699,
            "recall": 0.719,
        },
    ]
    accepted = core.analyze_runtime_comparison(
        rows,
        mode="live",
        minimum_throughput_improvement_percent=20,
        max_map50_regression=0.01,
        max_recall_regression=0.01,
    )
    assert accepted["adopt_tensorrt"] is True

    rows[1]["map50"] = 0.60
    rejected = core.analyze_runtime_comparison(
        rows,
        mode="live",
        minimum_throughput_improvement_percent=20,
        max_map50_regression=0.01,
        max_recall_regression=0.01,
    )
    assert rejected["adopt_tensorrt"] is False


def test_runner_defers_without_creating_an_engine(tmp_path: Path) -> None:
    output = tmp_path / "tensorrt.json"
    markdown = tmp_path / "tensorrt.md"
    workspace = tmp_path / "engine-workspace"
    subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--manifest",
            str(MANIFEST),
            "--output",
            str(output),
            "--markdown-output",
            str(markdown),
            "--workspace",
            str(workspace),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["decision"] == "deferred"
    assert report["prototype_executed"] is False
    assert report["production_runtime_changed"] is False
    assert {item["criterion"] for item in report["operational_comparison"]} == {
        "deployment_complexity",
        "model_management_burden",
        "rollback",
    }
    assert not workspace.exists()
