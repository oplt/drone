from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime


class NvbloxLogParser:
    """Thread-safe parser for nvBlox logs used by lifecycle restart logic."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.tf_jump_back_count = 0
        self.tf_old_data_count = 0
        self.restart_count = 0
        self.error_count = 0
        self.warning_count = 0
        self.last_tf_instability_at: float | None = None
        self.last_error_at: float | None = None
        self.last_warning_at: float | None = None
        self.last_error: str | None = None

    def ingest(self, line: str) -> tuple[int, bool]:
        text = str(line or "").strip()
        if not text:
            return logging.DEBUG, False
        lowered = text.lower()
        level = logging.DEBUG
        emit = False
        now = time.monotonic()
        with self._lock:
            if "detected jump back in time" in lowered or "jump back" in lowered:
                self.tf_jump_back_count += 1
                self.last_tf_instability_at = now
                self.warning_count += 1
                self.last_warning_at = now
                level = logging.WARNING
                emit = True
            elif "tf_old_data" in lowered:
                self.tf_old_data_count += 1
                self.last_tf_instability_at = now
                self.warning_count += 1
                self.last_warning_at = now
                level = logging.WARNING
                emit = True
            elif "error" in lowered or "exception" in lowered or "traceback" in lowered:
                self.error_count += 1
                self.last_error_at = now
                self.last_error = text[:500]
                level = logging.ERROR
                emit = True
            elif "warn" in lowered:
                self.warning_count += 1
                self.last_warning_at = now
                level = logging.WARNING
                emit = True
            elif "started up nvblox node" in lowered or "exited" in lowered:
                level = logging.INFO
                emit = True
        return level, emit

    def should_restart_for_tf_instability(
        self,
        *,
        jump_threshold: int,
        cooldown_s: float,
        last_restart_at: float,
    ) -> bool:
        with self._lock:
            jumps = self.tf_jump_back_count
        if jumps < max(1, int(jump_threshold)):
            return False
        return time.monotonic() - last_restart_at >= max(0.0, float(cooldown_s))

    def note_restart(self) -> None:
        with self._lock:
            self.restart_count += 1
            self.tf_jump_back_count = 0
            self.tf_old_data_count = 0
            self.last_tf_instability_at = None

    @staticmethod
    def _iso(monotonic_ts: float | None) -> str | None:
        if monotonic_ts is None:
            return None
        # Monotonic timestamps are not wall-clock timestamps; expose age instead in as_dict.
        return datetime.fromtimestamp(time.time() - (time.monotonic() - monotonic_ts), UTC).isoformat()

    def as_dict(self) -> dict[str, object]:
        with self._lock:
            now = time.monotonic()
            return {
                "available": True,
                "tf_jump_back_count": self.tf_jump_back_count,
                "tf_old_data_count": self.tf_old_data_count,
                "restart_count": self.restart_count,
                "error_count": self.error_count,
                "warning_count": self.warning_count,
                "last_tf_instability_age_s": (
                    round(now - self.last_tf_instability_at, 3)
                    if self.last_tf_instability_at is not None
                    else None
                ),
                "last_error_age_s": (
                    round(now - self.last_error_at, 3)
                    if self.last_error_at is not None
                    else None
                ),
                "last_warning_age_s": (
                    round(now - self.last_warning_at, 3)
                    if self.last_warning_at is not None
                    else None
                ),
                "last_error": self.last_error,
            }


nvblox_log_parser = NvbloxLogParser()
