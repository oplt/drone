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

# Historical Alembic revisions and large test modules are excluded from size
# metrics — migration immutability and golden tests outweigh line-count targets.
SKIP_PREFIXES: tuple[str, ...] = (
    "backend/infrastructure/persistence/alembic/versions/",
    "backend/tests/",
)


def effective_lines(path: Path) -> int:
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def should_skip(relative_path: str) -> bool:
    return relative_path.startswith(SKIP_PREFIXES)


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
        if should_skip(relative_path):
            continue
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


def evaluate_against_baseline(
    current: dict[str, dict[str, int]],
    baseline: dict[str, dict[str, int]],
) -> tuple[list[str], list[str], int]:
    """Return regressions, stale baseline paths, and grandfathered count."""
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

    stale = sorted(path for path in baseline if path not in current)
    return regressions, stale, grandfathered


def prune_baseline(baseline: dict[str, dict[str, int]], current: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    """Drop baseline entries for files that are now at or below their category limit."""
    return {path: baseline[path] for path in sorted(baseline) if path in current}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Record current violations as migration debt (drops resolved/stale entries).",
    )
    parser.add_argument(
        "--prune-baseline",
        action="store_true",
        help="Remove baseline entries for files now at or below their size limit.",
    )
    args = parser.parse_args()
    current = collect_violations()

    if args.update_baseline:
        BASELINE_PATH.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(f"Recorded {len(current)} existing file-size violations in baseline.")
        return 0

    if args.prune_baseline:
        baseline = load_baseline()
        pruned = prune_baseline(baseline, current)
        removed = sorted(set(baseline) - set(pruned))
        BASELINE_PATH.write_text(json.dumps(pruned, indent=2) + "\n", encoding="utf-8")
        print(f"Pruned {len(removed)} resolved baseline entries.")
        for path in removed:
            print(f"- {path}")
        return 0

    baseline = load_baseline()
    regressions, stale, grandfathered = evaluate_against_baseline(current, baseline)

    failed = False
    if stale:
        failed = True
        print("Stale file-size baseline entries (file is now at or below limit — remove them):")
        for path in stale:
            print(f"- {path}")
        print("Run: python backend/scripts/check_file_sizes.py --prune-baseline")

    if regressions:
        failed = True
        print("File-size architecture regressions:")
        for regression in regressions:
            print(f"- {regression}")

    if failed:
        return 1

    print(f"File-size guard passed; {grandfathered} baseline violations remain to extract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
