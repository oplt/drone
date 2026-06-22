from __future__ import annotations

from backend.modules.patrol.service.mission_runtime_store import (
    ActiveMissionRuntimeContext,
    mission_runtime_store,
)

_PRIVATE_PATROL_MISSION_TYPES = frozenset(
    {
        "private_patrol",
        "perimeter_patrol",
        "waypoint_patrol",
        "grid_surveillance",
        "event_triggered_patrol",
        "private_patrol_waypoint",
        "private_patrol_grid",
        "private_patrol_event_triggered",
    }
)


def is_private_patrol_context(ctx: ActiveMissionRuntimeContext | None) -> bool:
    if ctx is None:
        return False
    if ctx.private_patrol_task_type:
        return True
    mission_type = str(ctx.mission_type or "").strip().lower()
    return mission_type in _PRIVATE_PATROL_MISSION_TYPES


async def should_save_evidence_snapshot(*, save_debug_frames: bool) -> bool:
    """Private patrol flights rely on mission video recording, not JPEG snapshots."""
    if not save_debug_frames:
        return False
    ctx = await mission_runtime_store.get_active_context()
    return not is_private_patrol_context(ctx)
