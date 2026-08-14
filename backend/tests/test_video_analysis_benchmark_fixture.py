from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "backend/scripts/benchmarks/video_analysis_manifest.example.json"
SCRIPT = ROOT / "backend/scripts/benchmarks/run_video_analysis_benchmark.py"


def test_video_analysis_benchmark_fixture_mode_emits_report(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(MANIFEST),
            "--fixture",
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["mode"] == "fixture"
    assert report["runs"]["baseline"]["label"]
    assert report["runs"]["experiment"]["label"]
    assert report["parity"]["passed"] is True
