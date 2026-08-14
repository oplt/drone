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


class WarehouseExplorationFrontierMixin:
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
