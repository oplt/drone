#!/usr/bin/env python3
"""Run P2 static gates: one Alembic head, Ruff F821, and git diff --check."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOUCHED_MODULES = (
    "backend/modules/agriculture",
    "backend/modules/video_analysis/service",
    "backend/modules/vision_models/dataset_ingestion_operations.py",
    "backend/modules/vision_models/release_read_port.py",
)


def _run(command: list[str], *, cwd: Path = REPO_ROOT) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        raise RuntimeError(f"{' '.join(command)} failed:\n{output}")
    return result.stdout


def main() -> int:
    try:
        heads = _run(
            [sys.executable, "-m", "alembic", "-c", "alembic.ini", "heads"],
            cwd=REPO_ROOT / "backend",
        )
        head_lines = [line for line in heads.splitlines() if "(head)" in line]
        if len(head_lines) != 1:
            raise RuntimeError(
                f"Expected exactly one Alembic head, found {len(head_lines)}:\n{heads}"
            )
        _run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--select",
                "F821",
                *TOUCHED_MODULES,
            ]
        )
        _run(["git", "diff", "--check"])
    except RuntimeError as exc:
        print(exc)
        return 1
    print("P2 static gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
