#!/usr/bin/env python3
"""Fail when Ruff introduces new backend lint findings."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).with_name("ruff_baseline.json")
QUALITY_PATHS = (
    "backend/modules",
    "backend/infrastructure",
    "backend/entrypoints",
    "backend/core",
    "backend/tests",
    "backend/scripts",
)


def collect_findings() -> Counter[str]:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--output-format=json", *QUALITY_PATHS],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 1}:
        raise SystemExit(result.stdout + result.stderr)
    findings = cast(list[dict[str, Any]], json.loads(result.stdout or "[]"))
    counts: Counter[str] = Counter()
    for finding in findings:
        path = Path(str(finding["filename"])).relative_to(REPO_ROOT).as_posix()
        counts[f"{path}|{finding['code']}"] += 1
    return counts


def load_baseline() -> dict[str, int]:
    if not BASELINE_PATH.exists():
        raise SystemExit(
            f"Missing {BASELINE_PATH.relative_to(REPO_ROOT)}; "
            "run backend/scripts/check_ruff_baseline.py --update-baseline once."
        )
    return cast(dict[str, int], json.loads(BASELINE_PATH.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()
    current = collect_findings()
    if args.update_baseline:
        BASELINE_PATH.write_text(
            json.dumps(dict(sorted(current.items())), indent=2) + "\n", encoding="utf-8"
        )
        print(f"Recorded {sum(current.values())} existing Ruff findings in baseline.")
        return 0
    baseline = load_baseline()
    regressions = [
        f"{key}: {count} findings (baseline {baseline.get(key, 0)})"
        for key, count in sorted(current.items())
        if count > baseline.get(key, 0)
    ]
    if regressions:
        print("Ruff regressions:")
        for regression in regressions:
            print(f"- {regression}")
        return 1
    print(f"Ruff guard passed; {sum(current.values())} baseline findings remain to fix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
