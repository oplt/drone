from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = REPO_ROOT / "backend/scripts/benchmarks"
RUNNER = BENCHMARK_DIR / "run_video_precision_benchmark.py"
CORE = BENCHMARK_DIR / "precision_benchmark.py"
MANIFEST = BENCHMARK_DIR / "video_precision_manifest.example.json"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_fixture_gates_pass_numerically_but_cannot_promote() -> None:
    runner = _load(RUNNER, "run_video_precision_benchmark_fixture")
    core = _load(CORE, "precision_benchmark_fixture")
    manifest = runner.load_manifest(MANIFEST)
    rows = core.build_fixture_rows(manifest)
    report = runner.build_report(
        manifest,
        rows,
        mode="fixture",
        model_checksum=manifest["fixture_model_checksum"],
    )

    assert report["analysis"]["numeric_gates_pass"] is True
    assert report["analysis"]["promote_fp16"] is False
    assert report["production_default"] == "fp32"
    assert "Fixture data cannot promote" in report["analysis"]["reason"]


def test_live_evidence_promotes_only_when_accuracy_and_throughput_pass() -> None:
    core = _load(CORE, "precision_benchmark_live")
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["fixture_rows"]
    accepted = core.analyze_precision_rows(
        rows,
        mode="live",
        min_throughput_improvement_percent=15,
        max_map50_regression=0.01,
        max_recall_regression=0.01,
    )
    assert accepted["promote_fp16"] is True

    regressed = [dict(row) for row in rows]
    regressed[1]["map50"] = 0.60
    rejected = core.analyze_precision_rows(
        regressed,
        mode="live",
        min_throughput_improvement_percent=15,
        max_map50_regression=0.01,
        max_recall_regression=0.01,
    )
    assert rejected["promote_fp16"] is False


def test_precision_fixture_runner_writes_report_and_markdown(tmp_path: Path) -> None:
    output = tmp_path / "precision.json"
    markdown = tmp_path / "precision.md"
    subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--fixture",
            "--manifest",
            str(MANIFEST),
            "--output",
            str(output),
            "--markdown-output",
            str(markdown),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["mode"] == "fixture"
    assert report["analysis"]["promote_fp16"] is False
    assert "Production default: `fp32`" in markdown.read_text(encoding="utf-8")
