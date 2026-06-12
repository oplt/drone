from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class MappingStartupTiming:
    mission_start_monotonic: float
    marks: dict[str, float] = field(default_factory=dict)

    def note(self, mark: str) -> None:
        self.marks[mark] = time.monotonic()

    def as_dict(self) -> dict[str, int]:
        base = self.mission_start_monotonic
        return {
            f"{mark}_ms": int((value - base) * 1000)
            for mark, value in self.marks.items()
        }


_active: MappingStartupTiming | None = None


def begin_mapping_startup_timing(*, mission_start_monotonic: float) -> None:
    global _active
    _active = MappingStartupTiming(mission_start_monotonic=mission_start_monotonic)


def note_mapping_startup(mark: str) -> None:
    if _active is not None:
        _active.note(mark)


def active_mapping_startup_timing() -> MappingStartupTiming | None:
    return _active
