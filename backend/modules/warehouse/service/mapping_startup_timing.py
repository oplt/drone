from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field

_SAFE_MARK_RE = re.compile(r"[^A-Za-z0-9_.:-]+")


def _safe_mark(mark: str) -> str:
    cleaned = _SAFE_MARK_RE.sub("_", str(mark).strip())[:96].strip("._:-")
    return cleaned or "unknown"


@dataclass
class MappingStartupTiming:
    mission_start_monotonic: float
    marks: dict[str, float] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def note(self, mark: str) -> None:
        with self._lock:
            self.marks[_safe_mark(mark)] = time.monotonic()

    def as_dict(self) -> dict[str, int]:
        with self._lock:
            base = self.mission_start_monotonic
            return {
                f"{mark}_ms": max(0, int((value - base) * 1000))
                for mark, value in self.marks.items()
            }


_active: MappingStartupTiming | None = None
_active_lock = threading.RLock()


def begin_mapping_startup_timing(*, mission_start_monotonic: float | None = None) -> None:
    global _active
    start = time.monotonic() if mission_start_monotonic is None else float(mission_start_monotonic)
    with _active_lock:
        _active = MappingStartupTiming(mission_start_monotonic=start)


def end_mapping_startup_timing() -> MappingStartupTiming | None:
    global _active
    with _active_lock:
        previous = _active
        _active = None
        return previous


def note_mapping_startup(mark: str) -> None:
    with _active_lock:
        active = _active
    if active is not None:
        active.note(mark)


def active_mapping_startup_timing() -> MappingStartupTiming | None:
    with _active_lock:
        return _active
