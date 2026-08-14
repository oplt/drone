"""Warehouse mapping stack lifecycle — status model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WarehouseMappingStackStatus:
    running: bool
    pid: int | None = None
    started_at: str | None = None
    last_exit_code: int | None = None
    last_error: str | None = None
    nvblox_running: bool = False
    phase: str = "stopped"
    tf_degraded: bool = False
    nvblox_health: dict[str, object] = field(default_factory=dict)


__all__ = ["WarehouseMappingStackStatus"]
