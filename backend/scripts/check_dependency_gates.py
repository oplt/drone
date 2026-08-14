#!/usr/bin/env python3
"""Static gates for backend dependency hygiene (§14)."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

FORBIDDEN_REQUIREMENTS = ("passlib", "bcrypt")
FORBIDDEN_API_REQUIREMENTS = ("torch", "ultralytics", "ultralytics-thop", "sahi", "supervision")
ALLOWED_REQUESTS_PREFIXES = (
    "backend/infrastructure/camera/",
    "backend/observability/",
)
ASYNC_ROUTE_SUFFIXES = ("/routers/", "/api.py", "/websocket_api.py")
REQUESTS_IMPORT = re.compile(r"^\s*(?:import requests|from requests\b)")


def _read_requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-r"):
            continue
        names.add(line.split("==", 1)[0].split("[", 1)[0].strip().lower())
    return names


def _check_requirements() -> list[str]:
    errors: list[str] = []
    api_path = BACKEND_ROOT / "requirements-api.txt"
    api_names = _read_requirement_names(api_path)
    for forbidden in FORBIDDEN_REQUIREMENTS:
        if forbidden in api_names:
            errors.append(f"{api_path.name} must not list {forbidden!r}")
    for forbidden in FORBIDDEN_API_REQUIREMENTS:
        if forbidden in api_names:
            errors.append(f"{api_path.name} must not list ML package {forbidden!r}")

    for req_file in (BACKEND_ROOT / "requirements.txt", BACKEND_ROOT / "requirements-workers-ml.txt"):
        names = _read_requirement_names(req_file)
        for forbidden in FORBIDDEN_REQUIREMENTS:
            if forbidden in names:
                errors.append(f"{req_file.name} must not list {forbidden!r}")

    if "argon2-cffi" not in api_names:
        errors.append("requirements-api.txt must include argon2-cffi for password hashing")
    return errors


def _is_allowed_requests_path(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT).as_posix()
    return any(rel.startswith(prefix) for prefix in ALLOWED_REQUESTS_PREFIXES)


def _looks_like_async_route(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT).as_posix()
    return any(part in rel for part in ASYNC_ROUTE_SUFFIXES)


def _check_requests_imports() -> list[str]:
    errors: list[str] = []
    for path in BACKEND_ROOT.rglob("*.py"):
        if ".venv" in path.parts or path.name.startswith("."):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel.startswith("backend/tests/") or rel.startswith("backend/scripts/"):
            continue
        text = path.read_text(encoding="utf-8")
        if not REQUESTS_IMPORT.search(text):
            continue
        if _is_allowed_requests_path(path):
            continue
        if _looks_like_async_route(path):
            errors.append(
                f"sync requests import in async route module: {rel} "
                "(use httpx/aiohttp or run_blocking + infrastructure adapter)"
            )
            continue
        errors.append(
            f"sync requests import outside allowlist: {rel} "
            f"(allowed prefixes: {', '.join(ALLOWED_REQUESTS_PREFIXES)})"
        )
    return errors


def _check_patrol_runtime_lazy_ml() -> list[str]:
    runtime_path = BACKEND_ROOT / "modules/patrol/vision/runtime.py"
    tree = ast.parse(runtime_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith(
            "patrol.vision.pipeline"
        ):
            errors.append(
                "patrol vision runtime must not import DroneAnomalyPipeline at module scope"
            )
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "MLRuntimeManager":
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for sub in ast.walk(item):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                        if sub.func.id == "DroneAnomalyPipeline":
                            errors.append(
                                "patrol vision runtime must not construct DroneAnomalyPipeline "
                                "in __init__"
                            )
    return errors


def main() -> int:
    errors = [
        *_check_requirements(),
        *_check_requests_imports(),
        *_check_patrol_runtime_lazy_ml(),
    ]
    if errors:
        print("Dependency gates failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Dependency gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
