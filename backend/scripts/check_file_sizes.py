#!/usr/bin/env python3
"""Fail when Python files introduce or increase architecture size violations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
BASELINE_PATH = Path(__file__).with_name("file_size_baseline.json")


def effective_lines(path: Path) -> int:
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def limit_for(relative_path: str) -> int:
    if relative_path.startswith("backend/entrypoints/api/") or (
        relative_path.startswith("backend/modules/")
        and (
            "/api/" in relative_path
            or relative_path.endswith("/api.py")
            or relative_path.endswith("_api.py")
        )
    ):
        return 220
    if "/db/repository/" in relative_path:
        return 250
    if relative_path.startswith("backend/modules/") and (
        "/repository/" in relative_path
        or relative_path.endswith("/repository.py")
        or relative_path.endswith("_repository.py")
    ):
        return 250
    if relative_path.startswith("backend/modules/") and relative_path.endswith("/models.py"):
        return 250
    if relative_path.startswith("backend/modules/") and (
        relative_path.endswith("/service.py") or relative_path.endswith("/application.py")
    ):
        return 300
    if relative_path.startswith("backend/modules/") and (
        relative_path.endswith("/job.py") or relative_path.endswith("_job.py")
    ):
        return 280
    if relative_path.startswith("backend/modules/vehicle_runtime/"):
        if relative_path.endswith("/ports.py"):
            return 180
        return 300
    if relative_path.startswith("backend/infrastructure/"):
        return 260
    if "/schemas/" in relative_path:
        return 250
    if "/services/" in relative_path:
        return 300
    if relative_path.startswith("backend/entrypoints/workers/"):
        return 280
    return 400


def collect_violations() -> dict[str, dict[str, int]]:
    violations: dict[str, dict[str, int]] = {}
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        count = effective_lines(path)
        limit = limit_for(relative_path)
        if count > limit:
            violations[relative_path] = {"effective_lines": count, "limit": limit}
    return violations


def load_baseline() -> dict[str, dict[str, int]]:
    if not BASELINE_PATH.exists():
        raise SystemExit(
            f"Missing {BASELINE_PATH.relative_to(REPO_ROOT)}; "
            "run backend/scripts/check_file_sizes.py --update-baseline once."
        )
    return cast(
        dict[str, dict[str, int]],
        json.loads(BASELINE_PATH.read_text(encoding="utf-8")),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Record current violations as migration debt.",
    )
    args = parser.parse_args()
    current = collect_violations()

    if args.update_baseline:
        BASELINE_PATH.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(f"Recorded {len(current)} existing file-size violations in baseline.")
        return 0

    baseline = load_baseline()
    regressions: list[str] = []
    grandfathered = 0
    for path, violation in current.items():
        permitted = baseline.get(path)
        if permitted is not None and violation["effective_lines"] <= permitted["effective_lines"]:
            grandfathered += 1
            continue
        prior = permitted["effective_lines"] if permitted is not None else 0
        regressions.append(
            f"{path}: {violation['effective_lines']} effective lines "
            f"(limit {violation['limit']}, baseline {prior})"
        )

    if regressions:
        print("File-size architecture regressions:")
        for regression in regressions:
            print(f"- {regression}")
        return 1

    print(f"File-size guard passed; {grandfathered} baseline violations remain to extract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
