#!/usr/bin/env python3
"""Fail when strict mypy introduces new backend type errors."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).with_name("mypy_baseline.json")
ERROR_PATTERN = re.compile(r"^(backend/[^:]+):\d+(?::\d+)?: error: .+ \[([^\]]+)\]$")


def collect_errors() -> Counter[str]:
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "backend", "--no-error-summary", "--show-error-codes"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 1}:
        raise SystemExit(result.stdout + result.stderr)
    errors: Counter[str] = Counter()
    for line in result.stdout.splitlines():
        match = ERROR_PATTERN.match(line)
        if match:
            errors[f"{match.group(1)}|{match.group(2)}"] += 1
    return errors


def load_baseline() -> dict[str, int]:
    if not BASELINE_PATH.exists():
        raise SystemExit(
            f"Missing {BASELINE_PATH.relative_to(REPO_ROOT)}; "
            "run backend/scripts/check_mypy_baseline.py --update-baseline once."
        )
    return cast(dict[str, int], json.loads(BASELINE_PATH.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Record current strict mypy errors as migration debt.",
    )
    args = parser.parse_args()
    current = collect_errors()

    if args.update_baseline:
        BASELINE_PATH.write_text(
            json.dumps(dict(sorted(current.items())), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Recorded {sum(current.values())} existing mypy errors in baseline.")
        return 0

    baseline = load_baseline()
    regressions = [
        f"{key}: {count} errors (baseline {baseline.get(key, 0)})"
        for key, count in sorted(current.items())
        if count > baseline.get(key, 0)
    ]
    if regressions:
        print("Mypy regressions:")
        for regression in regressions:
            print(f"- {regression}")
        return 1

    print(f"Mypy guard passed; {sum(current.values())} baseline errors remain to fix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
