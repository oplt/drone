import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_guard(script_name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "backend" / "scripts" / script_name)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_file_size_guard_accepts_recorded_debt() -> None:
    result = _run_guard("check_file_sizes.py")

    assert result.returncode == 0, result.stdout + result.stderr


def test_boundary_guard_accepts_recorded_debt() -> None:
    result = _run_guard("check_backend_boundaries.py")

    assert result.returncode == 0, result.stdout + result.stderr


def test_mypy_guard_accepts_recorded_debt() -> None:
    result = _run_guard("check_mypy_baseline.py")

    assert result.returncode == 0, result.stdout + result.stderr


def test_ruff_guard_accepts_recorded_debt() -> None:
    result = _run_guard("check_ruff_baseline.py")

    assert result.returncode == 0, result.stdout + result.stderr
