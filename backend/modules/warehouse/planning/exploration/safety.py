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


class WarehouseExplorationSafetyMixin:
    async def _check_runtime_safety(
        self,
        orch: Orchestrator,
        *,
        health: SLAMHealth,
    ) -> WarehouseSafetyDecision:
        decision = evaluate_warehouse_runtime_safety(
            {
                "slam_tracking_ok": health.tracking_ok,
                "localization_confidence": health.localization_confidence,
                "odometry_drift_m": health.drift_estimate_m,
            },
            min_localization_confidence=float(self.localization_confidence_return_threshold),
            min_obstacle_distance_m=float(self.obstacle_clearance_m),
        )
        if decision.safe:
            return decision
        await self._add_event_safe(
            orch,
            "warehouse_safety_action",
            {
                "reason": decision.reason,
                "action": decision.action,
                "details": decision.details or {},
            },
        )
        await self._publish_status(
            orch,
            {
                "state": self._state.value,
                "safety_reason": decision.reason or "unknown",
                "safety_action": decision.action,
            },
        )
        return decision

    def _flight_elapsed_s(self) -> float:
        if self._mission_started_at <= 0:
            return 0.0
        return max(0.0, time.monotonic() - self._mission_started_at)

    async def _get_battery_remaining_pct(self, orch: Orchestrator) -> float:
        drone = getattr(orch, "drone", None)
        get_telemetry = getattr(drone, "get_telemetry", None)
        if not callable(get_telemetry):
            return 100.0
        try:
            telemetry = await asyncio.to_thread(get_telemetry)
        except Exception:
            logger.warning("Failed to read battery telemetry for indoor exploration", exc_info=True)
            return 100.0
        battery = getattr(telemetry, "battery_remaining", None)
        if battery is None:
            battery = getattr(telemetry, "battery_remaining_pct", None)
        if battery is None:
            return 100.0
        try:
            return max(0.0, min(100.0, float(battery)))
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid battery telemetry value: %r", battery)
            return 100.0
