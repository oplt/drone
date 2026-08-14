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


class WarehouseExplorationGraphMixin:
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
