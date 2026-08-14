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


class WarehouseExplorationProvidersMixin:
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
