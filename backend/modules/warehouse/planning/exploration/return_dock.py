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


class WarehouseExplorationReturnDockMixin:
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
