from __future__ import annotations

import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.core.logging.paths import runtime_log_root

logger = logging.getLogger(__name__)

DEFAULT_RUNTIME_LOG_RETENTION_DAYS = 14
MIN_RUNTIME_LOG_RETENTION_DAYS = 1


def runtime_log_retention_days() -> int:
    from backend.core.config.runtime import settings

    raw = str(settings.drone_runtime_log_retention_days)
    try:
        return max(MIN_RUNTIME_LOG_RETENTION_DAYS, int(raw))
    except ValueError:
        logger.warning(
            "Invalid DRONE_RUNTIME_LOG_RETENTION_DAYS=%r; using %d days",
            raw,
            DEFAULT_RUNTIME_LOG_RETENTION_DAYS,
        )
        return DEFAULT_RUNTIME_LOG_RETENTION_DAYS


def cleanup_runtime_logs(*, root: Path | None = None, retention_days: int | None = None) -> int:
    """Delete canonical runtime log files older than the configured retention window."""
    log_root = (root or runtime_log_root()).resolve()
    if not log_root.exists():
        return 0
    if not log_root.is_dir():
        logger.warning("Runtime log cleanup skipped because root is not a directory: %s", log_root)
        return 0

    days = retention_days if retention_days is not None else runtime_log_retention_days()
    cutoff = datetime.now(UTC) - timedelta(days=max(MIN_RUNTIME_LOG_RETENTION_DAYS, days))
    deleted = 0

    for path in log_root.rglob("*"):
        try:
            if not path.is_file():
                continue
            if path.stat().st_mtime >= cutoff.timestamp():
                continue
            path.unlink()
            deleted += 1
        except OSError:
            logger.warning("Failed to remove expired runtime log file: %s", path, exc_info=True)

    for directory in sorted((p for p in log_root.rglob("*") if p.is_dir()), reverse=True):
        with suppress(OSError):
            directory.rmdir()

    return deleted
