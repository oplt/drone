from __future__ import annotations

import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

_SOURCE_SEGMENT_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def _settings_string(name: str, default: str = "") -> str:
    try:
        from backend.core.config.runtime import settings

        value = getattr(settings, name, default)
    except Exception:
        value = default
    return str(value or "").strip()


def runtime_log_root() -> Path:
    """Canonical root for runtime logs produced by the application."""
    raw = _settings_string("drone_runtime_log_root")
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path.resolve()
    return (BACKEND_DIR / "storage" / "logs").resolve()


def runtime_log_dir(source: str) -> Path:
    """Return a source-specific runtime log directory under the canonical root."""
    normalized = _SOURCE_SEGMENT_RE.sub("_", str(source or "").strip().lower()).strip("._-")
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
