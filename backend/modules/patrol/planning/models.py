from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.modules.vehicle_runtime.types import Coordinate


@dataclass(frozen=True)
class PrivatePatrolPlan:
    waypoints: list[Coordinate]
    stats: dict[str, Any]


@dataclass(frozen=True)
class PatrolMLBinding:
    enabled: bool
    running: bool
    started_here: bool
    stream_source: str | int | None
    reason: str | None = None
