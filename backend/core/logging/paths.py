from __future__ import annotations

import os
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

_SOURCE_SEGMENT_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def runtime_log_root() -> Path:
    """Canonical root for runtime logs produced by the application."""
    raw = os.getenv("DRONE_RUNTIME_LOG_ROOT", "").strip()
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path.resolve()
    return (BACKEND_DIR / "storage" / "logs").resolve()


def runtime_log_dir(source: str) -> Path:
    """Return a source-specific runtime log directory under the canonical root."""
    normalized = _SOURCE_SEGMENT_RE.sub("_", source.strip().lower()).strip("._-")
    if not normalized:
        normalized = "backend"
    path = runtime_log_root() / normalized
    path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_runtime_log_roots() -> tuple[Path, ...]:
    """Old runtime log locations kept readable for diagnostics during migration."""
    return (
        (BACKEND_DIR / "logs").resolve(),
        (BACKEND_DIR / "storage" / "warehouse_ros" / "logs").resolve(),
    )
