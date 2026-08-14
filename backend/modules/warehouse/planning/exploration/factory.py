
from __future__ import annotations

from backend.modules.warehouse.planning.indoor import DockPose, LocalPose
from backend.modules.warehouse.planning.exploration.mission import UnknownWarehouseExplorationMission
from backend.modules.warehouse.planning.exploration.params import WarehouseExplorationMissionParams
from backend.modules.warehouse.planning.mission import WarehouseDockPoseParams

def _dock_pose_to_local_pose(
    pose: WarehouseDockPoseParams,
    *,
    frame_id: str = "map",
) -> LocalPose:
    return LocalPose(
        x_m=float(pose.x_m),
        y_m=float(pose.y_m),
        z_m=float(pose.z_m),
        yaw_deg=pose.yaw_deg,
        frame_id=frame_id,
    )


def build_unknown_warehouse_exploration_mission(
    *,
    hover_alt_m: float,
    exploration: WarehouseExplorationMissionParams,
    owner_id: int | None = None,
):
    if exploration.dock_config is None:
        raise ValueError(
            "indoor_exploration requires dock_config so launch and return anchors "
            "are defined in the local frame."
        )

    dock = DockPose(
        dock_id=(exploration.dock_pose_name or "dock").strip(),
        pose=_dock_pose_to_local_pose(exploration.dock_config.dock_pose),
        entry_pose=_dock_pose_to_local_pose(exploration.dock_config.entry_pose),
        exit_pose=_dock_pose_to_local_pose(exploration.dock_config.exit_pose),
        marker_id=exploration.dock_config.marker_id,
        precision_required=bool(exploration.dock_config.precision_required),
    )
    mission = UnknownWarehouseExplorationMission(
        dock=dock,
        warehouse_map_id=exploration.warehouse_map_id,
        warehouse_name=(exploration.warehouse_name or "").strip() or None,
        owner_id=owner_id,
        indoor_hover_alt_m=float(hover_alt_m),
        frontier_selection_strategy=exploration.frontier_selection_strategy,
        max_mission_time_s=float(exploration.max_mission_time_s),
        max_exploration_radius_m=float(exploration.max_exploration_radius_m),
        max_path_length_m=float(exploration.max_path_length_m),
        frontier_min_gain=float(exploration.frontier_min_gain),
        frontier_reach_timeout_s=float(exploration.frontier_reach_timeout_s),
        skeleton_build_radius_m=float(exploration.skeleton_build_radius_m),
        max_frontier_candidates=int(exploration.max_frontier_candidates),
        force_loop_closure_every_n_segments=int(exploration.force_loop_closure_every_n_segments),
        max_unknown_penetration_m=float(exploration.max_unknown_penetration_m),
        minimum_corridor_clearance_m=float(exploration.minimum_corridor_clearance_m),
        battery_return_reserve_pct=float(exploration.battery_return_reserve_pct),
        battery_emergency_land_reserve_pct=float(exploration.battery_emergency_land_reserve_pct),
        localization_confidence_min=float(exploration.localization_confidence_min),
        localization_confidence_return_threshold=float(
            exploration.localization_confidence_return_threshold
        ),
        obstacle_clearance_m=float(exploration.obstacle_clearance_m),
        relocalization_timeout_s=float(exploration.relocalization_timeout_s),
        backtrack_node_limit=int(exploration.backtrack_node_limit),
        safe_takeoff_bubble_radius_m=float(exploration.safe_takeoff_bubble_radius_m),
        dock_pose_name=exploration.dock_pose_name,
        dock_search_radius_m=float(exploration.dock_search_radius_m),
        dock_approach_speed_mps=float(exploration.dock_approach_speed_mps),
        dock_descent_speed_mps=float(exploration.dock_descent_speed_mps),
        docking_timeout_s=float(exploration.docking_timeout_s),
        occupancy_resolution_m=float(exploration.occupancy_resolution_m),
        voxel_resolution_m=exploration.voxel_resolution_m,
        map_update_hz=float(exploration.map_update_hz),
        map_snapshot_interval_s=float(exploration.map_snapshot_interval_s),
        loop_closure_preference_weight=float(exploration.loop_closure_preference_weight),
        explore_speed_mps=float(exploration.explore_speed_mps),
        transit_speed_mps=float(exploration.transit_speed_mps),
    )
    return mission, 0
