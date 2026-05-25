#!/usr/bin/env python3
"""Fail when backend changes introduce new forbidden layer imports."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
BASELINE_PATH = Path(__file__).with_name("boundary_baseline.json")


@dataclass(frozen=True)
class Rule:
    name: str
    source_prefix: str
    forbidden_prefixes: tuple[str, ...]


RULES = (
    Rule(
        "thin-module-api",
        "backend/modules/",
        ("sqlalchemy", "backend.core.database.models", "backend.entrypoints.workers"),
    ),
    Rule(
        "thin-worker-entrypoints",
        "backend/entrypoints/workers/",
        ("sqlalchemy", "backend.core.database", "backend.infrastructure"),
    ),
    Rule(
        "repositories-persistence-only",
        "backend/modules/",
        ("backend.entrypoints",),
    ),
    Rule(
        "schemas-no-workflows",
        "backend/modules/",
        ("backend.entrypoints",),
    ),
)


def imported_modules(path: Path) -> list[tuple[int, str]]:
    modules: list[tuple[int, str]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append((node.lineno, node.module))
    return modules


def collect_violations() -> dict[str, dict[str, object]]:
    violations: dict[str, dict[str, object]] = {}
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        for rule in RULES:
            if not relative_path.startswith(rule.source_prefix):
                continue
            if rule.name == "thin-module-api" and not (
                "/api/" in relative_path
                or relative_path.endswith("/api.py")
                or relative_path.endswith("_api.py")
            ):
                continue
            if rule.name == "repositories-persistence-only" and not (
                "/repository/" in relative_path or relative_path.endswith("/repository.py")
            ):
                continue
            if rule.name == "schemas-no-workflows" and "/schemas/" not in relative_path:
                continue
            for line, module in imported_modules(path):
                if module.startswith(rule.forbidden_prefixes):
                    key = f"{relative_path}|{rule.name}|{module}"
                    violations[key] = {
                        "path": relative_path,
                        "line": line,
                        "rule": rule.name,
                        "import": module,
                    }
    return violations


def load_baseline() -> dict[str, dict[str, object]]:
    if not BASELINE_PATH.exists():
        raise SystemExit(
            f"Missing {BASELINE_PATH.relative_to(REPO_ROOT)}; "
            "run backend/scripts/check_backend_boundaries.py --update-baseline once."
        )
    return cast(
        dict[str, dict[str, object]],
        json.loads(BASELINE_PATH.read_text(encoding="utf-8")),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Record current layer violations as migration debt.",
    )
    args = parser.parse_args()
    current = collect_violations()

    if args.update_baseline:
        BASELINE_PATH.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(f"Recorded {len(current)} existing boundary violations in baseline.")
        return 0

    baseline = load_baseline()
    regressions = [violation for key, violation in current.items() if key not in baseline]
    if regressions:
        print("Backend boundary regressions:")
        for violation in regressions:
            print(
                f"- {violation['path']}:{violation['line']} "
                f"[{violation['rule']}] imports {violation['import']}"
            )
        return 1

    print(f"Boundary guard passed; {len(current)} baseline violations remain to extract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
