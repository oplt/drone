"""Warehouse mapping stack lifecycle — nvblox log parsing with fallback."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class _OptionalProbeResult:
    def __init__(self, *, ok: bool = True, detail: str = "optional helper unavailable") -> None:
        self.ok = ok
        self.detail = detail

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "detail": self.detail}


class _FallbackNvbloxLogParser:
    tf_jump_back_count = 0
    tf_old_data_count = 0

    def ingest(self, line: str) -> tuple[int, bool]:
        lowered = line.lower()
        if "error" in lowered or "exception" in lowered:
            return logging.ERROR, True
        if "warn" in lowered or "tf_old_data" in lowered or "jump back" in lowered:
            if "tf_old_data" in lowered:
                self.tf_old_data_count += 1
            if "jump back" in lowered:
                self.tf_jump_back_count += 1
            return logging.WARNING, True
        if (
            "started up nvblox node" in lowered
            or "resizing gpu hash capacity" in lowered
            or "exited" in lowered
        ):
            return logging.INFO, True
        return logging.DEBUG, False

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
        self.tf_jump_back_count = 0
        self.tf_old_data_count = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "available": False,
            "warning": "nvblox_log_parser module unavailable; using inline fallback parser",
            "tf_jump_back_count": self.tf_jump_back_count,
            "tf_old_data_count": self.tf_old_data_count,
        }


_fallback_nvblox_log_parser: _FallbackNvbloxLogParser | None = None


def _get_nvblox_log_parser():
    global _fallback_nvblox_log_parser
    try:
        from backend.modules.warehouse.service.nvblox_log_parser import nvblox_log_parser

        return nvblox_log_parser
    except ModuleNotFoundError as exc:
        if _fallback_nvblox_log_parser is None:
            logger.warning("Optional nvblox log parser unavailable: %s", exc)
            _fallback_nvblox_log_parser = _FallbackNvbloxLogParser()
        return _fallback_nvblox_log_parser


__all__ = [
    "_FallbackNvbloxLogParser",
    "_OptionalProbeResult",
    "_get_nvblox_log_parser",
]
