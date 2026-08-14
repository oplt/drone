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


class WarehouseExplorationFlyMixin:
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
            await self._fly_exploration_teardown(
                orch,
                flight_token=flight_token,
                perception_started=perception_started,
                mapping_stack_started=mapping_stack_started,
            )

        await self._fly_exploration_finalize(
            orch,
            final_status=final_status,
            final_note=final_note,
            mission_error=mission_error,
        )
