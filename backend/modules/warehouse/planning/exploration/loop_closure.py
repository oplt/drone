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


class WarehouseExplorationLoopClosureMixin:
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
