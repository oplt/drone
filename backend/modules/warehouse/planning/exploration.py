from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, model_validator

from backend.modules.missions.flight_models import FlightStatus
from backend.modules.vehicle_runtime.types import Coordinate
from backend.modules.warehouse.planning.indoor import (
    DockingController,
    DockPose,
    DroneLocalNavigationAdapter,
    Frontier,
    FrontierExtractor,
    FrontierScorer,
    FrontierSelector,
    IndoorMissionState,
    LocalNavigationAdapter,
    LocalPose,
    LoopClosureScheduler,
    PrecisionDockingController,
    ReturnMarginEstimate,
    ReturnMarginEvaluator,
    SimulatedLocalNavigationAdapter,
    SimulatedSLAMProvider,
    SkeletonBuilder,
    SLAMHealth,
    SLAMProvider,
)
from backend.modules.warehouse.planning.mission import (
    WarehouseDockConfigParams,
    WarehouseDockPoseParams,
)
from backend.modules.warehouse.service.safety import (
    WarehouseSafetyDecision,
    evaluate_warehouse_runtime_safety,
)

if TYPE_CHECKING:
    from backend.modules.vehicle_runtime.orchestrator import Orchestrator
    from backend.modules.warehouse.planning.indoor import ExplorationGraph, MapSnapshot, SLAMHealth

logger = logging.getLogger(__name__)


class WarehouseExplorationMissionParams(BaseModel):
    warehouse_map_id: int | None = Field(default=None, ge=1)
    warehouse_name: str | None = Field(default=None, min_length=1, max_length=128)
    dock_config: WarehouseDockConfigParams | None = None
    frontier_selection_strategy: Literal["weighted_score"] = "weighted_score"
    max_mission_time_s: float = Field(default=900.0, gt=10.0, le=86_400.0)
    max_exploration_radius_m: float = Field(default=80.0, gt=1.0, le=2_000.0)
    max_path_length_m: float = Field(default=600.0, gt=1.0, le=10_000.0)
    frontier_min_gain: float = Field(default=1.0, ge=0.0, le=1_000.0)
    frontier_reach_timeout_s: float = Field(default=60.0, gt=1.0, le=3_600.0)
    skeleton_build_radius_m: float = Field(default=12.0, gt=0.5, le=500.0)
    max_frontier_candidates: int = Field(default=8, ge=1, le=100)
    force_loop_closure_every_n_segments: int = Field(default=3, ge=1, le=100)
    max_unknown_penetration_m: float = Field(default=2.0, ge=0.0, le=100.0)
    minimum_corridor_clearance_m: float = Field(default=1.0, gt=0.1, le=20.0)
    battery_return_reserve_pct: float = Field(default=30.0, ge=5.0, le=95.0)
    battery_emergency_land_reserve_pct: float = Field(default=20.0, ge=5.0, le=95.0)
    localization_confidence_min: float = Field(default=0.65, ge=0.0, le=1.0)
    localization_confidence_return_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    obstacle_clearance_m: float = Field(default=0.8, gt=0.1, le=20.0)
    relocalization_timeout_s: float = Field(default=15.0, gt=1.0, le=600.0)
    backtrack_node_limit: int = Field(default=6, ge=1, le=100)
    safe_takeoff_bubble_radius_m: float = Field(default=1.5, gt=0.1, le=20.0)
    dock_pose_name: str = Field(default="dock", min_length=1, max_length=128)
    dock_search_radius_m: float = Field(default=1.5, gt=0.1, le=25.0)
    dock_approach_speed_mps: float = Field(default=0.3, gt=0.05, le=5.0)
    dock_descent_speed_mps: float = Field(default=0.15, gt=0.01, le=2.0)
    docking_timeout_s: float = Field(default=90.0, gt=5.0, le=3_600.0)
    occupancy_resolution_m: float = Field(default=0.5, gt=0.05, le=5.0)
    voxel_resolution_m: float | None = Field(default=None, gt=0.01, le=5.0)
    map_update_hz: float = Field(default=2.0, gt=0.1, le=50.0)
    map_snapshot_interval_s: float = Field(default=5.0, gt=0.2, le=600.0)
    loop_closure_preference_weight: float = Field(default=1.0, ge=0.0, le=10.0)
    explore_speed_mps: float = Field(default=0.8, gt=0.05, le=10.0)
    transit_speed_mps: float = Field(default=1.1, gt=0.05, le=15.0)

    @model_validator(mode="after")
    def validate_reserves(self) -> WarehouseExplorationMissionParams:
        if self.battery_return_reserve_pct <= self.battery_emergency_land_reserve_pct:
            raise ValueError(
                "battery_return_reserve_pct must exceed battery_emergency_land_reserve_pct"
            )
        return self


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


@dataclass
class UnknownWarehouseExplorationMission:
    dock: DockPose
    warehouse_map_id: int | None = None
    warehouse_name: str | None = None
    owner_id: int | None = None

    indoor_hover_alt_m: float = 2.5
    frontier_selection_strategy: str = "weighted_score"
    max_mission_time_s: float = 900.0
    max_exploration_radius_m: float = 80.0
    max_path_length_m: float = 600.0
    frontier_min_gain: float = 1.0
    frontier_reach_timeout_s: float = 60.0
    skeleton_build_radius_m: float = 12.0
    max_frontier_candidates: int = 8
    force_loop_closure_every_n_segments: int = 3
    max_unknown_penetration_m: float = 2.0
    minimum_corridor_clearance_m: float = 1.0
    battery_return_reserve_pct: float = 30.0
    battery_emergency_land_reserve_pct: float = 20.0
    localization_confidence_min: float = 0.65
    localization_confidence_return_threshold: float = 0.5
    obstacle_clearance_m: float = 0.8
    relocalization_timeout_s: float = 15.0
    backtrack_node_limit: int = 6
    safe_takeoff_bubble_radius_m: float = 1.5
    dock_pose_name: str = "dock"
    dock_search_radius_m: float = 1.5
    dock_approach_speed_mps: float = 0.3
    dock_descent_speed_mps: float = 0.15
    docking_timeout_s: float = 90.0
    occupancy_resolution_m: float = 0.5
    voxel_resolution_m: float | None = None
    map_update_hz: float = 2.0
    map_snapshot_interval_s: float = 5.0
    loop_closure_preference_weight: float = 1.0
    explore_speed_mps: float = 0.8
    transit_speed_mps: float = 1.1

    slam_provider: SLAMProvider | None = field(default=None, repr=False, compare=False)
    navigator: LocalNavigationAdapter | None = field(default=None, repr=False, compare=False)
    dock_controller: DockingController | None = field(default=None, repr=False, compare=False)

    mission_type: str = field(default="indoor_exploration", init=False)
    _state: IndoorMissionState = field(
        default=IndoorMissionState.IDLE_AT_DOCK, init=False, repr=False
    )
    _state_history: list[IndoorMissionState] = field(default_factory=list, init=False, repr=False)
    _graph: ExplorationGraph | None = field(default=None, init=False, repr=False)
    _mission_started_at: float = field(default=0.0, init=False, repr=False)
    _last_snapshot_event_at: float = field(default=0.0, init=False, repr=False)
    _segments_completed: int = field(default=0, init=False, repr=False)
    _docked_successfully: bool = field(default=False, init=False, repr=False)

    @property
    def state_history(self) -> list[str]:
        return [state.value for state in self._state_history]

    def get_waypoints(self) -> list[Coordinate]:
        return []

    def get_flight_record_anchor(self, alt: float) -> tuple[Coordinate, Coordinate, str]:
        placeholder = Coordinate(lat=0.0, lon=0.0, alt=float(alt))
        return placeholder, placeholder, "indoor_local_placeholder"

    def get_preflight_mission_data(self) -> dict[str, object]:
        dock = self.dock
        return {
            "type": "indoor_exploration",
            "waypoints": [],
            "speed": float(self.transit_speed_mps),
            "altitude_agl": float(self.indoor_hover_alt_m),
            "dock": {
                "dock_id": dock.dock_id,
                "pose": self._pose_dict(dock.pose),
                "entry_pose": self._pose_dict(dock.entry_pose),
                "exit_pose": self._pose_dict(dock.exit_pose),
                "marker_id": dock.marker_id,
                "precision_required": bool(dock.precision_required),
            },
            "safe_takeoff_bubble_radius_m": float(self.safe_takeoff_bubble_radius_m),
            "battery_return_reserve_pct": float(self.battery_return_reserve_pct),
            "battery_emergency_land_reserve_pct": float(self.battery_emergency_land_reserve_pct),
            "localization_confidence_min": float(self.localization_confidence_min),
            "localization_confidence_return_threshold": float(
                self.localization_confidence_return_threshold
            ),
            "obstacle_clearance_m": float(self.obstacle_clearance_m),
            "minimum_corridor_clearance_m": float(self.minimum_corridor_clearance_m),
            "max_mission_time_s": float(self.max_mission_time_s),
            "max_exploration_radius_m": float(self.max_exploration_radius_m),
            "max_path_length_m": float(self.max_path_length_m),
            "frontier_min_gain": float(self.frontier_min_gain),
            "skeleton_build_radius_m": float(self.skeleton_build_radius_m),
            "force_loop_closure_every_n_segments": int(self.force_loop_closure_every_n_segments),
            "max_unknown_penetration_m": float(self.max_unknown_penetration_m),
            "dock_search_radius_m": float(self.dock_search_radius_m),
            "dock_approach_speed_mps": float(self.dock_approach_speed_mps),
            "dock_descent_speed_mps": float(self.dock_descent_speed_mps),
            "docking_timeout_s": float(self.docking_timeout_s),
            "occupancy_resolution_m": float(self.occupancy_resolution_m),
            "map_update_hz": float(self.map_update_hz),
            "loop_closure_preference_weight": float(self.loop_closure_preference_weight),
            "backtrack_node_limit": int(self.backtrack_node_limit),
            "local_control_mode": "local_setpoint",
        }

    async def execute(self, orch: Orchestrator, *, alt: float = 2.5) -> None:
        if not math.isclose(float(alt), float(self.indoor_hover_alt_m), abs_tol=1e-6):
            self.indoor_hover_alt_m = float(alt)
        await orch.run_mission(
            self,
            alt=float(self.indoor_hover_alt_m),
            flight_fn=lambda: self.fly_exploration(orch),
        )

    async def fly_exploration(self, orch: Orchestrator) -> None:
        self._mission_started_at = time.monotonic()
        self._last_snapshot_event_at = 0.0
        self._segments_completed = 0
        self._docked_successfully = False
        self._state_history = []

        slam = self._resolve_slam_provider(orch)
        navigator = self._resolve_navigator(orch, slam)
        dock_controller = self._resolve_dock_controller(navigator)

        from backend.modules.warehouse.planning.indoor import ExplorationGraph

        self._graph = ExplorationGraph()
        skeleton_builder = SkeletonBuilder(self._graph)
        frontier_extractor = FrontierExtractor(
            obstacle_clearance_m=self.obstacle_clearance_m,
            minimum_corridor_clearance_m=self.minimum_corridor_clearance_m,
        )
        frontier_scorer = FrontierScorer()
        frontier_selector = FrontierSelector(strategy=self.frontier_selection_strategy)
        return_evaluator = ReturnMarginEvaluator(
            max_path_length_m=float(self.max_path_length_m),
            max_mission_time_s=float(self.max_mission_time_s),
            battery_return_reserve_pct=float(self.battery_return_reserve_pct),
            battery_emergency_land_reserve_pct=float(self.battery_emergency_land_reserve_pct),
            nominal_speed_mps=max(0.1, float(self.transit_speed_mps)),
        )
        loop_scheduler = LoopClosureScheduler(
            every_n_segments=int(self.force_loop_closure_every_n_segments),
            preference_weight=float(self.loop_closure_preference_weight),
        )

        mission_error: Exception | None = None
        final_status = FlightStatus.FAILED
        final_note = "Indoor warehouse exploration failed"
        perception_started = False
        mapping_stack_started = False
        from backend.modules.warehouse.service.capture_finalize import (
            safe_flight_token,
            start_warehouse_ros_mapping,
            stop_warehouse_ros_mapping,
        )

        flight_token = safe_flight_token(
            getattr(orch, "current_client_flight_id", None)
            or getattr(orch, "_flight_id", None)
        )

        try:
            await self._add_event_safe(
                orch,
                "indoor_mission_created",
                {
                    "warehouse_map_id": self.warehouse_map_id,
                    "warehouse_name": self.warehouse_name,
                    "dock_id": self.dock.dock_id,
                    "hover_alt_m": float(self.indoor_hover_alt_m),
                },
            )
            await self._transition(orch, IndoorMissionState.INDOOR_PREFLIGHT)
            await self._add_event_safe(
                orch, "indoor_preflight_passed", {"dock_id": self.dock.dock_id}
            )

            if self.warehouse_map_id is not None:
                mapping_stack_started = True
                mapping_start = await start_warehouse_ros_mapping(
                    flight_id=flight_token,
                    warehouse_map_id=int(self.warehouse_map_id),
                    metadata={
                        "mission_kind": "indoor_exploration",
                        "warehouse_name": self.warehouse_name,
                    },
                )
                perception_started = bool(mapping_start.accepted)
                await self._add_event_safe(
                    orch,
                    "indoor_exploration_mapping_started",
                    {
                        "accepted": mapping_start.accepted,
                        "status": mapping_start.status,
                        "detail": mapping_start.detail,
                    },
                )

            dock_initialized = await dock_controller.initialize_dock_reference(self.dock)
            if not dock_initialized:
                raise RuntimeError("Dock reference initialization failed")
            self._graph.ensure_dock_node(self.dock)
            await self._add_event_safe(
                orch,
                "dock_initialized",
                {"dock": self._dock_dict(self.dock)},
            )

            await self._transition(orch, IndoorMissionState.TAKEOFF_SAFE_BUBBLE)
            await navigator.arm_and_takeoff_local(float(self.indoor_hover_alt_m))
            await self._add_event_safe(
                orch,
                "safe_bubble_takeoff",
                {
                    "hover_alt_m": float(self.indoor_hover_alt_m),
                    "bubble_radius_m": float(self.safe_takeoff_bubble_radius_m),
                },
            )

            await self._transition(orch, IndoorMissionState.BOOTSTRAP_LOCAL_MAP)
            await self._add_event_safe(orch, "slam_bootstrap_started", {})
            bootstrap_path = self._bootstrap_scan_path()
            if bootstrap_path:
                await navigator.follow_local_path(
                    bootstrap_path,
                    speed_mps=min(0.5, float(self.explore_speed_mps)),
                    timeout_s=float(self.frontier_reach_timeout_s),
                )
            bootstrap_health = await slam.get_localization_health()
            if float(bootstrap_health.localization_confidence) < float(
                self.localization_confidence_min
            ):
                raise RuntimeError(
                    "SLAM bootstrap did not reach the minimum localization confidence"
                )
            snapshot = await slam.get_map_snapshot()
            await self._emit_snapshot_status(orch, snapshot)
            await self._add_event_safe(
                orch,
                "slam_bootstrap_completed",
                {
                    "localization_confidence": float(bootstrap_health.localization_confidence),
                    "free_cells": int(snapshot.free_cells),
                    "occupied_cells": int(snapshot.occupied_cells),
                },
            )

            await self._transition(orch, IndoorMissionState.BUILD_SKELETON)
            seeded_nodes = skeleton_builder.seed_from_snapshot(
                snapshot=snapshot,
                dock=self.dock,
                radius_m=float(self.skeleton_build_radius_m),
                localization_confidence=float(bootstrap_health.localization_confidence),
            )
            await self._add_event_safe(
                orch,
                "indoor_skeleton_seeded",
                {"nodes": len(seeded_nodes)},
            )

            segments_since_loop = 0
            while True:
                await self._transition(orch, IndoorMissionState.CHECK_RETURN_MARGIN)
                current_pose = await slam.get_pose()
                health = await slam.get_localization_health()
                decision = await self._check_runtime_safety(orch, health=health)
                if not decision.safe:
                    if decision.action in {"return_or_land", "return_or_relocalize"}:
                        break
                    raise RuntimeError(f"Indoor exploration safety abort: {decision.reason}")

                if float(health.localization_confidence) < float(self.localization_confidence_min):
                    recovered = await self._handle_localization_degradation(
                        orch=orch,
                        slam=slam,
                        navigator=navigator,
                    )
                    if not recovered:
                        if await self._can_return_to_dock(slam):
                            break
                        raise RuntimeError(
                            "Localization could not be recovered and no safe return path remained"
                        )
                    current_pose = await slam.get_pose()
                    health = await slam.get_localization_health()

                snapshot = await slam.get_map_snapshot()
                await self._emit_snapshot_status(orch, snapshot)

                if self._should_force_return(orch, current_pose):
                    break

                if loop_scheduler.should_run(
                    segments_since_last=segments_since_loop,
                    drift_estimate_m=float(health.drift_estimate_m),
                ):
                    loop_success = await self._run_loop_closure(
                        orch=orch,
                        slam=slam,
                        navigator=navigator,
                        snapshot=snapshot,
                        current_pose=current_pose,
                    )
                    if loop_success:
                        segments_since_loop = 0
                        continue

                await self._transition(orch, IndoorMissionState.SELECT_FRONTIER)
                selected = await self._select_frontier(
                    orch=orch,
                    slam=slam,
                    snapshot=snapshot,
                    current_pose=current_pose,
                    health=health,
                    frontier_extractor=frontier_extractor,
                    frontier_scorer=frontier_scorer,
                    frontier_selector=frontier_selector,
                    return_evaluator=return_evaluator,
                )

                if selected is None:
                    break

                await self._transition(orch, IndoorMissionState.TRANSIT_TO_FRONTIER)
                transit_path = snapshot.occupancy_grid.astar_path(
                    current_pose,
                    selected.approach_pose,
                    clearance_m=float(self.obstacle_clearance_m),
                )
                if not transit_path:
                    await self._add_event_safe(
                        orch,
                        "frontier_rejected",
                        {"frontier_id": selected.frontier_id, "reason": "path_blocked"},
                    )
                    continue

                await self._add_event_safe(
                    orch,
                    "frontier_selected",
                    self._frontier_event_payload(selected),
                )
                await navigator.follow_local_path(
                    transit_path,
                    speed_mps=float(self.transit_speed_mps),
                    timeout_s=float(self.frontier_reach_timeout_s),
                )
                await self._add_event_safe(
                    orch,
                    "frontier_reached",
                    {"frontier_id": selected.frontier_id},
                )

                await self._transition(orch, IndoorMissionState.MAP_FRONTIER_REGION)
                probe_path = self._build_frontier_probe_path(
                    snapshot=snapshot,
                    frontier=selected,
                )
                if probe_path:
                    await navigator.follow_local_path(
                        probe_path,
                        speed_mps=float(self.explore_speed_mps),
                        timeout_s=float(self.frontier_reach_timeout_s),
                    )

                reached_pose = await slam.get_pose()
                reached_health = await slam.get_localization_health()
                self._register_confirmed_node(
                    pose=reached_pose,
                    confidence=float(reached_health.localization_confidence),
                    kind="frontier",
                )
                self._segments_completed += 1
                segments_since_loop += 1

                if float(reached_health.localization_confidence) <= float(
                    self.localization_confidence_return_threshold
                ):
                    await self._add_event_safe(
                        orch,
                        "return_margin_low",
                        {"reason": "localization_return_threshold"},
                    )
                    break

            await self._transition(orch, IndoorMissionState.RETURN_TO_DOCK)
            await self._add_event_safe(orch, "return_to_dock_started", {})
            returned = await self._return_to_dock(
                orch=orch,
                slam=slam,
                navigator=navigator,
            )
            if not returned:
                raise RuntimeError("Unable to compute a safe return path to dock")

            await self._transition(orch, IndoorMissionState.PRECISION_DOCK)
            await self._add_event_safe(orch, "docking_started", {"dock_id": self.dock.dock_id})
            docked = await self._run_precision_docking(
                orch=orch,
                slam=slam,
                dock_controller=dock_controller,
                navigator=navigator,
            )
            if not docked:
                raise RuntimeError("Precision docking did not complete successfully")
            self._docked_successfully = True

            await self._transition(orch, IndoorMissionState.LAND_AND_FINALIZE)
            await navigator.wait_until_disarmed(float(self.docking_timeout_s))
            await self._add_event_safe(orch, "docking_completed", {"dock_id": self.dock.dock_id})
            final_status = FlightStatus.COMPLETED
            final_note = "Indoor warehouse exploration completed and docked successfully"

        except Exception as exc:
            mission_error = exc
            logger.exception("Indoor warehouse exploration mission failed")
            safe_landed = await self._safe_land(
                orch=orch,
                navigator=navigator,
                reason=str(exc),
            )
            if safe_landed:
                final_note = f"Indoor exploration ended in safe land: {exc}"
            else:
                final_note = f"Indoor exploration failed: {exc}"
            final_status = FlightStatus.FAILED

        finally:
            if perception_started:
                from backend.modules.warehouse.service.capture_finalize import (
                    persist_warehouse_ros_capture,
                )
                from backend.modules.warehouse.service.mapping import WarehouseScanMappingError

                try:
                    stop_result = await stop_warehouse_ros_mapping(flight_id=flight_token)
                except Exception as exc:
                    stop_result = None
                    await self._add_event_safe(
                        orch,
                        "indoor_exploration_mapping_stop_failed",
                        {"error": str(exc)},
                    )
                    logger.exception("Indoor exploration mapping stop failed flight_id=%s", flight_token)
                if stop_result is not None:
                    await self._add_event_safe(
                        orch,
                        "indoor_exploration_mapping_stopped",
                        {
                            "accepted": stop_result.accepted,
                            "status": stop_result.status,
                            "detail": stop_result.detail,
                        },
                    )
                if (
                    stop_result is not None
                    and stop_result.accepted
                    and self.owner_id is not None
                    and self.warehouse_map_id is not None
                ):
                    stop_data = stop_result.data if isinstance(stop_result.data, dict) else None
                    try:
                        mapping_result = await persist_warehouse_ros_capture(
                            flight_id=flight_token,
                            owner_id=int(self.owner_id),
                            org_id=None,
                            source="indoor_exploration",
                            stop_data=stop_data,
                            warehouse_map_id=int(self.warehouse_map_id),
                            warehouse_name=self.warehouse_name,
                            db_flight_id=getattr(orch, "_flight_id", None),
                            mission_kind="indoor_exploration",
                        )
                        await self._add_event_safe(
                            orch,
                            "indoor_exploration_mapping_saved",
                            mapping_result,
                        )
                    except WarehouseScanMappingError as exc:
                        await self._add_event_safe(
                            orch,
                            "indoor_exploration_mapping_failed",
                            {"error": str(exc)},
                        )
                        logger.warning(
                            "Indoor exploration mapping persistence failed flight_id=%s error=%s",
                            flight_token,
                            exc,
                        )
            if mapping_stack_started:
                from backend.modules.warehouse.service.mapping_stack_lifecycle import (
                    shutdown_warehouse_mapping_stack,
                )

                try:
                    await shutdown_warehouse_mapping_stack()
                except Exception as exc:
                    await self._add_event_safe(
                        orch,
                        "indoor_exploration_mapping_cleanup_failed",
                        {"error": str(exc)},
                    )
                    logger.warning("Indoor exploration mapping stack shutdown failed", exc_info=True)

        await self._finish_flight_safe(orch, status=final_status, note=final_note)

        event_type = (
            "indoor_mission_completed"
            if final_status == FlightStatus.COMPLETED
            else "indoor_mission_failed"
        )
        await self._add_event_safe(
            orch,
            event_type,
            {
                "state": self._state.value,
                "segments_completed": int(self._segments_completed),
                "docked": bool(self._docked_successfully),
                "flight_status": final_status.value,
                "error": str(mission_error) if mission_error is not None else None,
            },
        )

        if mission_error is not None:
            raise mission_error

    def _resolve_slam_provider(self, orch: Orchestrator) -> SLAMProvider:
        if self.slam_provider is not None:
            return self.slam_provider
        for target in (orch, getattr(orch, "drone", None)):
            if target is None:
                continue
            for attr in (
                "indoor_slam_provider",
                "slam_provider",
                "localization_provider",
            ):
                provider = getattr(target, attr, None)
                if provider is not None:
                    self.slam_provider = provider
                    return provider
        from backend.modules.warehouse.service.exploration_slam import (
            WarehousePerceptionSLAMProvider,
        )

        self.slam_provider = WarehousePerceptionSLAMProvider()
        return self.slam_provider

    def _resolve_navigator(
        self,
        orch: Orchestrator,
        slam: SLAMProvider,
    ) -> LocalNavigationAdapter:
        if self.navigator is not None:
            return self.navigator
        drone = getattr(orch, "drone", None)
        if drone is None and isinstance(slam, SimulatedSLAMProvider):
            self.navigator = SimulatedLocalNavigationAdapter(slam)
            return self.navigator
        if drone is None:
            raise RuntimeError(
                "Indoor exploration requires a local navigation adapter or an active drone"
            )
        self.navigator = DroneLocalNavigationAdapter(drone=drone, slam_provider=slam)
        return self.navigator

    def _resolve_dock_controller(
        self,
        navigator: LocalNavigationAdapter,
    ) -> DockingController:
        if self.dock_controller is not None:
            return self.dock_controller
        self.dock_controller = PrecisionDockingController(
            navigator=navigator,
            dock_search_radius_m=float(self.dock_search_radius_m),
            approach_speed_mps=float(self.dock_approach_speed_mps),
            descent_speed_mps=float(self.dock_descent_speed_mps),
        )
        return self.dock_controller

    def _bootstrap_scan_path(self) -> list[LocalPose]:
        radius = min(
            max(0.4, float(self.safe_takeoff_bubble_radius_m) * 0.65),
            1.25,
        )
        base = self.dock.exit_pose.translated(
            dz_m=float(self.indoor_hover_alt_m) - float(self.dock.exit_pose.z_m)
        )
        return [
            base,
            base.translated(dx_m=radius),
            base.translated(dy_m=radius),
            base.translated(dx_m=-radius),
            base.translated(dy_m=-radius),
            base,
        ]

    async def _emit_snapshot_status(self, orch: Orchestrator, snapshot: MapSnapshot) -> None:
        now = time.monotonic()
        if (now - self._last_snapshot_event_at) < float(self.map_snapshot_interval_s):
            return
        self._last_snapshot_event_at = now
        payload = {
            "state": self._state.value,
            "free_cells": int(snapshot.free_cells),
            "occupied_cells": int(snapshot.occupied_cells),
            "explored_cells": int(snapshot.explored_cells),
        }
        if getattr(orch, "mqtt", None):
            try:
                orch.mqtt.publish("drone/indoor_exploration/status", payload, qos=1)
            except Exception:
                logger.exception("Failed publishing indoor exploration status to MQTT")
        await self._add_event_safe(orch, "indoor_map_snapshot", payload)

    async def _transition(self, orch: Orchestrator, state: IndoorMissionState) -> None:
        self._state = state
        self._state_history.append(state)
        await self._publish_status(
            orch,
            {
                "state": state.value,
                "elapsed_s": round(self._flight_elapsed_s(), 2),
            },
        )

    async def _publish_status(self, orch: Orchestrator, payload: dict[str, object]) -> None:
        if getattr(orch, "mqtt", None):
            try:
                orch.mqtt.publish("drone/indoor_exploration/status", payload, qos=1)
            except Exception:
                logger.exception("Failed publishing indoor exploration status to MQTT")

    async def _check_runtime_safety(
        self,
        orch: Orchestrator,
        *,
        health: SLAMHealth,
    ) -> WarehouseSafetyDecision:
        decision = evaluate_warehouse_runtime_safety(
            {
                "slam_tracking_ok": health.tracking_ok,
                "localization_confidence": health.localization_confidence,
                "odometry_drift_m": health.drift_estimate_m,
            },
            min_localization_confidence=float(self.localization_confidence_return_threshold),
            min_obstacle_distance_m=float(self.obstacle_clearance_m),
        )
        if decision.safe:
            return decision
        await self._add_event_safe(
            orch,
            "warehouse_safety_action",
            {
                "reason": decision.reason,
                "action": decision.action,
                "details": decision.details or {},
            },
        )
        await self._publish_status(
            orch,
            {
                "state": self._state.value,
                "safety_reason": decision.reason or "unknown",
                "safety_action": decision.action,
            },
        )
        return decision

    def _flight_elapsed_s(self) -> float:
        if self._mission_started_at <= 0:
            return 0.0
        return max(0.0, time.monotonic() - self._mission_started_at)

    async def _get_battery_remaining_pct(self, orch: Orchestrator) -> float:
        drone = getattr(orch, "drone", None)
        get_telemetry = getattr(drone, "get_telemetry", None)
        if not callable(get_telemetry):
            return 100.0
        try:
            telemetry = await asyncio.to_thread(get_telemetry)
        except Exception:
            logger.warning("Failed to read battery telemetry for indoor exploration", exc_info=True)
            return 100.0
        battery = getattr(telemetry, "battery_remaining", None)
        if battery is None:
            battery = getattr(telemetry, "battery_remaining_pct", None)
        if battery is None:
            return 100.0
        try:
            return max(0.0, min(100.0, float(battery)))
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid battery telemetry value: %r", battery)
            return 100.0

    def _register_confirmed_node(self, *, pose: LocalPose, confidence: float, kind: str) -> None:
        if self._graph is None:
            return
        nearest = self._graph.nearest_node(pose, confirmed_only=True, max_distance_m=0.8)
        if nearest is not None:
            return
        neighbor = self._graph.nearest_node(pose, confirmed_only=True, max_distance_m=6.0)
        dock_connected = pose.planar_distance_to(self.dock.pose) <= float(
            self.max_exploration_radius_m
        )
        node = self._graph.add_node(
            pose,
            confidence=float(confidence),
            connected_to_dock=bool(dock_connected),
            kind=kind,
        )
        if neighbor is not None and neighbor.node_id != node.node_id:
            self._graph.connect_nodes(
                node.node_id,
                neighbor.node_id,
                node.pose.planar_distance_to(neighbor.pose),
            )

    async def _select_frontier(
        self,
        *,
        orch: Orchestrator,
        slam: SLAMProvider,
        snapshot: MapSnapshot,
        current_pose: LocalPose,
        health: SLAMHealth,
        frontier_extractor: FrontierExtractor,
        frontier_scorer: FrontierScorer,
        frontier_selector: FrontierSelector,
        return_evaluator: ReturnMarginEvaluator,
    ) -> Frontier | None:
        del slam
        if self._graph is None:
            return None

        raw_frontiers = frontier_extractor.extract(
            snapshot=snapshot,
            current_pose=current_pose,
            graph=self._graph,
            localization_confidence=float(health.localization_confidence),
        )
        viable: list[Frontier] = []
        battery_remaining_pct = await self._get_battery_remaining_pct(orch)
        skeleton_phase = self._segments_completed == 0

        for frontier in raw_frontiers:
            if float(frontier.information_gain) < float(self.frontier_min_gain):
                await self._add_event_safe(
                    orch,
                    "frontier_rejected",
                    {
                        "frontier_id": frontier.frontier_id,
                        "reason": "low_information_gain",
                    },
                )
                continue
            if frontier.centroid.planar_distance_to(self.dock.pose) > float(
                self.max_exploration_radius_m
            ):
                await self._add_event_safe(
                    orch,
                    "frontier_rejected",
                    {
                        "frontier_id": frontier.frontier_id,
                        "reason": "beyond_radius_limit",
                    },
                )
                continue
            return_path = snapshot.occupancy_grid.astar_path(
                frontier.approach_pose,
                self.dock.entry_pose,
                clearance_m=float(self.obstacle_clearance_m),
            )
            if not return_path:
                await self._add_event_safe(
                    orch,
                    "frontier_rejected",
                    {
                        "frontier_id": frontier.frontier_id,
                        "reason": "no_safe_return_path",
                    },
                )
                continue
            margin = return_evaluator.evaluate(
                battery_remaining_pct=float(battery_remaining_pct),
                outbound_path_length_m=float(frontier.path_length_m),
                explore_buffer_m=float(self.max_unknown_penetration_m),
                return_path_length_m=snapshot.occupancy_grid.path_length_m(return_path),
                elapsed_s=self._flight_elapsed_s(),
            )
            if not margin.can_continue:
                await self._add_event_safe(
                    orch,
                    "frontier_rejected",
                    {
                        "frontier_id": frontier.frontier_id,
                        "reason": margin.reason,
                        "projected_remaining_pct": round(float(margin.projected_remaining_pct), 2),
                    },
                )
                if not margin.can_return:
                    await self._add_event_safe(
                        orch,
                        "return_margin_low",
                        {"reason": margin.reason},
                    )
                continue
            enriched = self._frontier_with_margin(frontier, margin)
            viable.append(
                frontier_scorer.score(
                    enriched,
                    skeleton_phase=skeleton_phase,
                    loop_closure_due=(
                        self._segments_completed >= self.force_loop_closure_every_n_segments
                    ),
                )
            )

        ranked = frontier_selector.rank(
            viable,
            max_candidates=int(self.max_frontier_candidates),
        )
        return ranked[0] if ranked else None

    @staticmethod
    def _frontier_with_margin(frontier: Frontier, margin: ReturnMarginEstimate) -> Frontier:
        metadata = dict(frontier.metadata)
        metadata["return_margin_reason"] = margin.reason
        metadata["projected_remaining_pct"] = float(margin.projected_remaining_pct)
        metadata["return_path_length_m"] = float(margin.return_path_length_m)
        return replace(
            frontier,
            battery_cost_pct=float(margin.total_cost_pct),
            metadata=metadata,
        )

    def _build_frontier_probe_path(
        self,
        *,
        snapshot: MapSnapshot,
        frontier: Frontier,
    ) -> list[LocalPose]:
        raw_cells = frontier.metadata.get("cells", [])
        if not isinstance(raw_cells, list) or not raw_cells:
            return []
        limit = max(
            1,
            int(
                math.ceil(
                    float(self.max_unknown_penetration_m)
                    / float(snapshot.occupancy_grid.resolution_m)
                )
            ),
        )
        poses: list[LocalPose] = []
        for raw_cell in raw_cells[:limit]:
            if (
                not isinstance(raw_cell, tuple)
                or len(raw_cell) != 2
                or not all(isinstance(value, int) for value in raw_cell)
            ):
                continue
            x_idx, y_idx = raw_cell
            poses.append(
                snapshot.occupancy_grid.cell_to_pose(
                    x_idx,
                    y_idx,
                    z_m=float(self.indoor_hover_alt_m),
                )
            )
        return poses

    async def _run_loop_closure(
        self,
        *,
        orch: Orchestrator,
        slam: SLAMProvider,
        navigator: LocalNavigationAdapter,
        snapshot: MapSnapshot,
        current_pose: LocalPose,
    ) -> bool:
        if self._graph is None:
            return False
        await self._transition(orch, IndoorMissionState.FORCE_LOOP_CLOSURE)
        scheduler = LoopClosureScheduler(
            every_n_segments=int(self.force_loop_closure_every_n_segments),
            preference_weight=float(self.loop_closure_preference_weight),
        )
        target = scheduler.choose_target(graph=self._graph, current_pose=current_pose)
        if target is None:
            return False
        path = snapshot.occupancy_grid.astar_path(
            current_pose,
            target.pose,
            clearance_m=float(self.obstacle_clearance_m),
        )
        if not path:
            return False
        await self._add_event_safe(
            orch,
            "loop_closure_requested",
            {"target_node_id": target.node_id},
        )
        await navigator.follow_local_path(
            path,
            speed_mps=float(self.transit_speed_mps),
            timeout_s=float(self.frontier_reach_timeout_s),
        )
        await slam.optimize_map()
        await self._add_event_safe(
            orch,
            "loop_closure_completed",
            {"target_node_id": target.node_id},
        )
        return True

    async def _handle_localization_degradation(
        self,
        *,
        orch: Orchestrator,
        slam: SLAMProvider,
        navigator: LocalNavigationAdapter,
    ) -> bool:
        await self._add_event_safe(
            orch,
            "localization_degraded",
            {"state": self._state.value},
        )
        await self._transition(orch, IndoorMissionState.PAUSE_RELOCALIZE)
        await navigator.hold_position(timeout_s=1.0)
        await self._add_event_safe(orch, "relocalization_started", {})
        if await slam.relocalize(float(self.relocalization_timeout_s)):
            health = await slam.get_localization_health()
            if float(health.localization_confidence) >= float(self.localization_confidence_min):
                return True
        await self._add_event_safe(orch, "relocalization_failed", {})

        await self._transition(orch, IndoorMissionState.BACKTRACK_TO_CONFIRMED_NODE)
        if self._graph is None:
            return False
        snapshot = await slam.get_map_snapshot()
        current_pose = await slam.get_pose()
        for node in self._graph.backtrack_candidates(limit=int(self.backtrack_node_limit)):
            path = snapshot.occupancy_grid.astar_path(
                current_pose,
                node.pose,
                clearance_m=float(self.obstacle_clearance_m),
            )
            if not path:
                continue
            await self._add_event_safe(
                orch,
                "backtrack_started",
                {"target_node_id": node.node_id},
            )
            await navigator.follow_local_path(
                path,
                speed_mps=float(self.transit_speed_mps),
                timeout_s=float(self.frontier_reach_timeout_s),
            )
            health = await slam.get_localization_health()
            if float(health.localization_confidence) >= float(self.localization_confidence_min):
                return True
        return False

    async def _can_return_to_dock(self, slam: SLAMProvider) -> bool:
        snapshot = await slam.get_map_snapshot()
        current_pose = await slam.get_pose()
        return bool(
            snapshot.occupancy_grid.astar_path(
                current_pose,
                self.dock.entry_pose,
                clearance_m=float(self.obstacle_clearance_m),
            )
        )

    def _should_force_return(self, orch: Orchestrator, current_pose: LocalPose) -> bool:
        del orch
        if self._flight_elapsed_s() >= float(self.max_mission_time_s):
            return True
        return current_pose.planar_distance_to(self.dock.pose) >= float(
            self.max_exploration_radius_m
        )

    async def _return_to_dock(
        self,
        *,
        orch: Orchestrator,
        slam: SLAMProvider,
        navigator: LocalNavigationAdapter,
    ) -> bool:
        snapshot = await slam.get_map_snapshot()
        current_pose = await slam.get_pose()
        route = snapshot.occupancy_grid.astar_path(
            current_pose,
            self.dock.entry_pose,
            clearance_m=float(self.obstacle_clearance_m),
        )
        if not route and self._graph is not None:
            current_node = self._graph.nearest_node(current_pose, confirmed_only=True)
            dock_node = self._graph.ensure_dock_node(self.dock)
            if current_node is not None:
                node_route = self._graph.shortest_path(current_node.node_id, dock_node.node_id)
                route = [current_pose]
                for node in node_route[1:]:
                    leg = snapshot.occupancy_grid.astar_path(
                        route[-1],
                        node.pose,
                        clearance_m=float(self.obstacle_clearance_m),
                    )
                    if not leg:
                        route = []
                        break
                    route.extend(leg[1:])
                if route:
                    tail = snapshot.occupancy_grid.astar_path(
                        route[-1],
                        self.dock.entry_pose,
                        clearance_m=float(self.obstacle_clearance_m),
                    )
                    if not tail:
                        route = []
                    else:
                        route.extend(tail[1:])
        if not route:
            await self._add_event_safe(
                orch,
                "return_margin_low",
                {"reason": "no_safe_route_to_dock"},
            )
            return False

        await navigator.follow_local_path(
            route,
            speed_mps=float(self.transit_speed_mps),
            timeout_s=float(self.frontier_reach_timeout_s),
        )
        return True

    async def _run_precision_docking(
        self,
        *,
        orch: Orchestrator,
        slam: SLAMProvider,
        dock_controller: DockingController,
        navigator: LocalNavigationAdapter,
    ) -> bool:
        current_pose = await slam.get_pose()
        if await dock_controller.run_precision_docking(current_pose, self.dock):
            return True

        # Bounded search near dock, then retry once.
        search_path = self._dock_search_path()
        if search_path:
            await navigator.follow_local_path(
                search_path,
                speed_mps=float(self.dock_approach_speed_mps),
                timeout_s=float(self.docking_timeout_s),
            )
        current_pose = await slam.get_pose()
        if await dock_controller.run_precision_docking(current_pose, self.dock):
            return True
        return False

    def _dock_search_path(self) -> list[LocalPose]:
        radius = min(1.0, float(self.dock_search_radius_m))
        search_z_m = max(float(self.indoor_hover_alt_m), float(self.dock.entry_pose.z_m))

        def _at_search_height(pose: LocalPose) -> LocalPose:
            return LocalPose(
                x_m=float(pose.x_m),
                y_m=float(pose.y_m),
                z_m=search_z_m,
                yaw_deg=pose.yaw_deg,
                frame_id=pose.frame_id,
            )

        dock_center = _at_search_height(self.dock.pose)
        entry = _at_search_height(self.dock.entry_pose)
        return [
            entry,
            dock_center.translated(dx_m=radius),
            dock_center.translated(dy_m=radius),
            dock_center.translated(dx_m=-radius),
            dock_center.translated(dy_m=-radius),
            entry,
        ]

    async def _safe_land(
        self,
        *,
        orch: Orchestrator,
        navigator: LocalNavigationAdapter,
        reason: str,
    ) -> bool:
        await self._transition(orch, IndoorMissionState.SAFE_LAND)
        await self._add_event_safe(
            orch,
            "safe_land_triggered",
            {"reason": reason},
        )
        try:
            await navigator.safe_land()
            await navigator.wait_until_disarmed(float(self.docking_timeout_s))
            return True
        except Exception:
            logger.exception("Indoor exploration safe land failed")
            return False

    async def _finish_flight_safe(
        self,
        orch: Orchestrator,
        *,
        status: FlightStatus,
        note: str,
    ) -> bool:
        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is None:
            return False
        safe_note = (note or "").strip()
        if len(safe_note) > 250:
            safe_note = safe_note[:247] + "..."
        try:
            await orch.repo.finish_flight(flight_id, status=status, note=safe_note)
            return True
        except Exception:
            logger.exception(
                "UnknownWarehouseExplorationMission: failed to finish flight_id=%s",
                flight_id,
            )
            return False

    async def _add_event_safe(
        self,
        orch: Orchestrator,
        event_type: str,
        data: dict | None = None,
    ) -> None:
        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is None:
            return
        try:
            await orch.repo.add_event(flight_id, event_type, data or {})
        except Exception:
            logger.exception(
                "UnknownWarehouseExplorationMission: failed to persist event '%s' (flight_id=%s)",
                event_type,
                flight_id,
            )

    @staticmethod
    def _pose_dict(pose: LocalPose) -> dict[str, object]:
        return {
            "x_m": float(pose.x_m),
            "y_m": float(pose.y_m),
            "z_m": float(pose.z_m),
            "yaw_deg": pose.yaw_deg,
            "frame_id": pose.frame_id,
        }

    def _dock_dict(self, dock: DockPose) -> dict[str, object]:
        return {
            "dock_id": dock.dock_id,
            "marker_id": dock.marker_id,
            "pose": self._pose_dict(dock.pose),
            "entry_pose": self._pose_dict(dock.entry_pose),
            "exit_pose": self._pose_dict(dock.exit_pose),
            "precision_required": bool(dock.precision_required),
        }

    def _frontier_event_payload(self, frontier: Frontier) -> dict[str, object]:
        return {
            "frontier_id": frontier.frontier_id,
            "score": round(float(frontier.score), 3),
            "information_gain": round(float(frontier.information_gain), 3),
            "path_length_m": round(float(frontier.path_length_m), 2),
            "clearance_m": round(float(frontier.clearance_m), 2),
            "localization_confidence": round(float(frontier.localization_confidence), 3),
            "battery_cost_pct": round(float(frontier.battery_cost_pct), 2),
            "centroid": self._pose_dict(frontier.centroid),
            "approach_pose": self._pose_dict(frontier.approach_pose),
        }
