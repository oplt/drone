from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    REPO_ROOT
    / "backend/scripts/benchmarks/video_decoder_manifest.example.json"
)
RUNNER = REPO_ROOT / "backend/scripts/benchmarks/run_video_decoder_benchmark.py"


@pytest.fixture()
def manifest() -> dict:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_video_decoder_benchmark",
        REPO_ROOT / "backend/scripts/benchmarks/run_video_decoder_benchmark.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.load_manifest(MANIFEST)


def test_fixture_manifest_builds_report_rows(manifest: dict) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_video_decoder_benchmark",
        REPO_ROOT / "backend/scripts/benchmarks/run_video_decoder_benchmark.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    rows = module.build_fixture_rows(manifest)
    assert len(rows) == len(manifest["clips"]) * len(manifest["sample_rates_fps"]) * len(
        manifest["modes"]
    )
    report = module.build_report(manifest, rows, mode="fixture")
    assert report["gates"]["production_default_decoder"] == "opencv_sequential"
    assert report["adoption"]["recommend_default_change"] is False
    markdown = module.render_markdown(report)
    assert "Timing methodology" in markdown
    assert "opencv_sequential" in markdown


def test_live_opencv_sequential_on_synthetic_video(tmp_path: Path) -> None:
    pytest.importorskip("cv2")
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "video_decoder_modes",
        REPO_ROOT / "backend/scripts/benchmarks/video_decoder_modes.py",
    )
    modes = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modes)

    video_path = tmp_path / "short.mp4"
    modes.write_synthetic_video(video_path, fps=30.0, frame_count=90, width=320, height=240)
    result = modes.benchmark_decoder_mode(
        modes.MODE_OPENCV_SEQUENTIAL,
        video_path,
        sample_rate_fps=1.0,
        sample_ram=lambda: None,
    )
    assert result.available is True
    assert result.decoded_frames == 90
    assert result.selected_frames == 3
    assert result.wall_time_seconds >= 0.0


def test_cli_fixture_mode_writes_json_and_csv(tmp_path: Path) -> None:
    json_out = tmp_path / "report.json"
    csv_out = tmp_path / "report.csv"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--manifest",
            str(MANIFEST),
            "--fixture",
            "--output",
            str(json_out),
            "--csv-output",
            str(csv_out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.returncode == 0
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["mode"] == "fixture"
    assert payload["rows"]
    assert csv_out.read_text(encoding="utf-8").splitlines()[0].startswith("clip_id,")
