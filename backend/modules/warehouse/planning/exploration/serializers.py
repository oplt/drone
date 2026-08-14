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


class WarehouseExplorationSerializersMixin:
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
