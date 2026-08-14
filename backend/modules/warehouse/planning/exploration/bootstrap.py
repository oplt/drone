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


class WarehouseExplorationBootstrapMixin:
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
