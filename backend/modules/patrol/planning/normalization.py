from __future__ import annotations

from collections.abc import Iterable

from backend.modules.patrol.ai_tasks import coerce_ai_tasks
from backend.modules.patrol.planning.types import PatrolDirection, PatrolTask


def normalize_ai_tasks(tasks: Iterable[str] | None) -> tuple[PatrolTask, ...]:
    return coerce_ai_tasks(tasks)


def normalize_patrol_direction(
    direction: str | PatrolDirection | None,
) -> PatrolDirection:
    raw = str(direction or "clockwise").strip().lower().replace("_", "-")
    if raw in {"clockwise", "cw"}:
        return "clockwise"
    if raw in {"counterclockwise", "counter-clockwise", "ccw"}:
        return "counterclockwise"
    raise ValueError("direction must be 'clockwise' or 'counterclockwise'")
