#!/usr/bin/env python3
"""Verify characterization test coverage exists before splitting behavior-heavy modules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = Path(__file__).with_name("characterization_registry.json")


def load_registry() -> dict:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if payload.get("version") != 1:
        raise SystemExit(f"Unsupported characterization registry version: {payload.get('version')!r}")
    return payload


def collect_gaps(*, phase: int | None = None, require_tests: bool = False) -> list[str]:
    registry = load_registry()
    gaps: list[str] = []
    for entry in registry.get("entries", []):
        entry_phase = int(entry.get("phase", 0))
        if phase is not None and entry_phase != phase:
            continue
        source = str(entry["source"])
        source_path = REPO_ROOT / source
        if not source_path.exists():
            gaps.append(f"{source}: source file missing")
            continue
        tests = entry.get("tests") or []
        if require_tests and not tests:
            gaps.append(f"{source}: no characterization tests registered (phase {entry_phase})")
            continue
        for test_path in tests:
            if not (REPO_ROOT / test_path).exists():
                gaps.append(f"{source}: missing test {test_path}")
    return gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        type=int,
        default=None,
        help="Only validate entries tagged with this roadmap phase.",
    )
    parser.add_argument(
        "--require-tests",
        action="store_true",
        help="Fail when a registered source has zero characterization tests.",
    )
    args = parser.parse_args()

    gaps = collect_gaps(phase=args.phase, require_tests=args.require_tests)
    if gaps:
        print("Characterization registry gaps:")
        for gap in gaps:
            print(f"- {gap}")
        return 1

    scope = f"phase {args.phase}" if args.phase is not None else "all phases"
    print(f"Characterization registry OK ({scope}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
