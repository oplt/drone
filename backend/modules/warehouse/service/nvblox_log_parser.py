from __future__ import annotations

import logging
import time


class NvbloxLogParser:
    def __init__(self) -> None:
        self.tf_jump_back_count = 0
        self.tf_old_data_count = 0
        self.restart_count = 0
        self.last_tf_instability_at: float | None = None

    def ingest(self, line: str) -> tuple[int, bool]:
        lowered = line.lower()
        emit = False
        level = logging.DEBUG
        if "detected jump back in time" in lowered or "jump back" in lowered:
            self.tf_jump_back_count += 1
            self.last_tf_instability_at = time.monotonic()
            level = logging.WARNING
            emit = True
        elif "tf_old_data" in lowered:
            self.tf_old_data_count += 1
            self.last_tf_instability_at = time.monotonic()
            level = logging.WARNING
            emit = True
        elif "error" in lowered or "exception" in lowered:
            level = logging.ERROR
            emit = True
        elif "warn" in lowered:
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
        if self.tf_jump_back_count < max(1, int(jump_threshold)):
            return False
        return time.monotonic() - last_restart_at >= max(0.0, float(cooldown_s))

    def note_restart(self) -> None:
        self.restart_count += 1
        self.tf_jump_back_count = 0
        self.tf_old_data_count = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "available": True,
            "tf_jump_back_count": self.tf_jump_back_count,
            "tf_old_data_count": self.tf_old_data_count,
            "restart_count": self.restart_count,
            "last_tf_instability_at": self.last_tf_instability_at,
        }


nvblox_log_parser = NvbloxLogParser()
