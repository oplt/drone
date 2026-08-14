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
