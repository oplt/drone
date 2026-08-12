#!/usr/bin/env python3
"""Enforce DTO/service boundaries between Agriculture, Video, and Vision."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULES_ROOT = REPO_ROOT / "backend" / "modules"

# Application contracts are the only allowed Video Analysis integration surface
# for ORM/repository concerns. Other Video Analysis modules (e.g. service helpers)
# may still be shared where they do not expose ORM entities.
VIDEO_ANALYSIS_ORM_OR_REPO = frozenset(
    {
        "backend.modules.video_analysis.repository",
        "backend.modules.video_analysis.models",
    }
)


@dataclass(frozen=True, slots=True)
class Violation:
    path: str
    line: int
    imported: str
    reason: str


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
    return found


def _is_vision_orm(module: str) -> bool:
    return module.startswith("backend.modules.vision_models.") and (
        module.endswith("models") or ".models." in module
    )


def _is_video_analysis_orm_or_repo(module: str) -> bool:
    if module == "backend.modules.video_analysis.contracts":
        return False
    return module in VIDEO_ANALYSIS_ORM_OR_REPO or module.startswith(
        "backend.modules.video_analysis.models."
    )


def collect_violations(modules_root: Path = MODULES_ROOT) -> list[Violation]:
    violations: list[Violation] = []
    for path in sorted(modules_root.rglob("*.py")):
        try:
            relative = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            relative = path.as_posix()
        for line, imported in _imports(path):
            reason = None
            if "/agriculture/" in relative and (
                _is_video_analysis_orm_or_repo(imported) or _is_vision_orm(imported)
            ):
                reason = (
                    "Agriculture must consume Video/Vision via "
                    "backend.modules.video_analysis.contracts (or Vision ports), "
                    "not ORM/repositories"
                )
            elif "/video_analysis/" in relative and imported in {
                "backend.modules.agriculture.models",
                "backend.modules.agriculture.repository",
            }:
                reason = "Video must consume Agriculture contracts/ports"
            elif "/vision_models/" in relative and imported in {
                "backend.modules.agriculture.models",
                "backend.modules.agriculture.repository",
            }:
                reason = "Vision must consume Agriculture contracts/ports"
            elif "/vision_models/" in relative and _is_video_analysis_orm_or_repo(
                imported
            ):
                reason = (
                    "Vision must consume Video via "
                    "backend.modules.video_analysis.contracts, not ORM/repositories"
                )
            if reason:
                violations.append(Violation(relative, line, imported, reason))
    return violations


def main() -> int:
    violations = collect_violations()
    if not violations:
        print("Module port guard passed.")
        return 0
    print("Module port violations:")
    for violation in violations:
        print(
            f"- {violation.path}:{violation.line} imports {violation.imported}: "
            f"{violation.reason}"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
