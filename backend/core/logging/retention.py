from __future__ import annotations

import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.core.logging.paths import runtime_log_root

logger = logging.getLogger(__name__)

DEFAULT_RUNTIME_LOG_RETENTION_DAYS = 14
MIN_RUNTIME_LOG_RETENTION_DAYS = 1
LOG_SUFFIXES = {".log", ".txt", ".json", ".jsonl", ".out", ".err"}


def runtime_log_retention_days() -> int:
    from backend.core.config.runtime import settings

    raw = str(getattr(settings, "drone_runtime_log_retention_days", DEFAULT_RUNTIME_LOG_RETENTION_DAYS))
    try:
        return max(MIN_RUNTIME_LOG_RETENTION_DAYS, int(raw))
    except (TypeError, ValueError):
        logger.warning(
            "Invalid DRONE_RUNTIME_LOG_RETENTION_DAYS=%r; using %d days",
            raw,
            DEFAULT_RUNTIME_LOG_RETENTION_DAYS,
        )
        return DEFAULT_RUNTIME_LOG_RETENTION_DAYS


def cleanup_runtime_logs(*, root: Path | None = None, retention_days: int | None = None) -> int:
    """Delete canonical runtime log files older than the configured retention window.

    The cleanup now only removes known log-like file extensions and skips
    symlinks, preventing accidental deletion of unrelated files under the log
    root.
    """
    log_root = (root or runtime_log_root()).resolve()
    if not log_root.exists():
        return 0
    if not log_root.is_dir():
        logger.warning("Runtime log cleanup skipped because root is not a directory: %s", log_root)
        return 0

    try:
        days = int(retention_days) if retention_days is not None else runtime_log_retention_days()
    except (TypeError, ValueError):
        days = DEFAULT_RUNTIME_LOG_RETENTION_DAYS
    cutoff = datetime.now(UTC) - timedelta(days=max(MIN_RUNTIME_LOG_RETENTION_DAYS, days))
    cutoff_ts = cutoff.timestamp()
    deleted = 0

    for path in log_root.rglob("*"):
        try:
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix.lower() not in LOG_SUFFIXES:
                continue
            path.resolve().relative_to(log_root)
            if path.stat().st_mtime >= cutoff_ts:
                continue
            path.unlink()
            deleted += 1
        except OSError:
            logger.warning("Failed to remove expired runtime log file: %s", path, exc_info=True)
        except ValueError:
            logger.warning("Skipping runtime log outside root: %s", path)

    for directory in sorted((p for p in log_root.rglob("*") if p.is_dir()), reverse=True):
        with suppress(OSError):
            directory.rmdir()

    return deleted
