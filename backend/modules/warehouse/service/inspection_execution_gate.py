from __future__ import annotations

from backend.modules.warehouse.service.slam_localization_monitor import slam_localization_snapshot
from backend.modules.warehouse.service.slam_localization_probe import refresh_slam_localization_from_ros

_SLAM_LOCALIZATION_METHODS = frozenset(
    {"live_slam", "provisional_slam", "scan_provisional", "vslam"}
)


def uses_live_slam_localization(localization_method: str | None) -> bool:
    return str(localization_method or "").strip().lower() in _SLAM_LOCALIZATION_METHODS


async def localization_runtime_gate(
    localization_method: str | None,
    *,
    probe_ros: bool = True,
) -> str | None:
    """Return an execution-stop reason when localization is unsafe during a mission."""
    if not uses_live_slam_localization(localization_method):
        return None
    if probe_ros:
        await refresh_slam_localization_from_ros()
    snapshot = slam_localization_snapshot()
    if snapshot.get("healthy"):
        return None
    return "localization_unhealthy"
