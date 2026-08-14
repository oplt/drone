"""Target routing priority assignment."""

from __future__ import annotations

from backend.modules.warehouse.planning.indoor.models import LocalPose, OccupancyGrid
from backend.modules.warehouse.schemas import WAREHOUSE_MAP_FRAME_ID

from .models import GeneratedTarget


def _assign_serpentine_priority(targets: list[GeneratedTarget]) -> None:
    """Aisle-aware serpentine ordering -> priority (lower flies first)."""
    by_aisle: dict[str, list[GeneratedTarget]] = {}
    for tgt in targets:
        by_aisle.setdefault(tgt.aisle_code, []).append(tgt)

    priority = 0
    for serpentine_idx, aisle_code in enumerate(sorted(by_aisle)):
        group = by_aisle[aisle_code]
        group.sort(key=lambda t: (t.target_point["x_m"], t.target_point["y_m"], t.shelf_level))
        if serpentine_idx % 2 == 1:
            group.reverse()
        for tgt in group:
            tgt.priority = priority
            priority += 1


def _pose_for_target(target: GeneratedTarget) -> LocalPose:
    pose = target.scan_pose
    return LocalPose(
        x_m=float(pose["x_m"]),
        y_m=float(pose["y_m"]),
        z_m=float(pose.get("z_m", 0.0)),
        yaw_deg=float(pose["yaw_deg"]) if pose.get("yaw_deg") is not None else None,
        frame_id=str(pose.get("frame_id") or WAREHOUSE_MAP_FRAME_ID),
    )


def _assign_astar_priority(
    targets: list[GeneratedTarget],
    *,
    occupancy_grid: OccupancyGrid,
    clearance_m: float,
) -> None:
    """Collision-aware target order using OccupancyGrid.astar_path path length."""
    if len(targets) <= 1:
        _assign_serpentine_priority(targets)
        return

    remaining = sorted(
        targets,
        key=lambda t: (
            str(t.aisle_code),
            str(t.rack_code),
            int(t.shelf_level),
            str(t.bin_code),
        ),
    )
    ordered: list[GeneratedTarget] = [remaining.pop(0)]
    current_pose = _pose_for_target(ordered[0])

    while remaining:
        best_index = 0
        best_cost = float("inf")
        for idx, candidate in enumerate(remaining):
            candidate_pose = _pose_for_target(candidate)
            path = occupancy_grid.astar_path(
                current_pose,
                candidate_pose,
                clearance_m=clearance_m,
            )
            if path:
                cost = occupancy_grid.path_length_m(path)
            else:
                cost = current_pose.planar_distance_to(candidate_pose) + 1_000_000.0
            if cost < best_cost:
                best_index = idx
                best_cost = cost
        selected = remaining.pop(best_index)
        ordered.append(selected)
        current_pose = _pose_for_target(selected)

    for priority, target in enumerate(ordered):
        target.priority = priority
