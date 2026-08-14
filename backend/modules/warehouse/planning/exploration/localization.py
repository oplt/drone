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


class WarehouseExplorationLocalizationMixin:
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
