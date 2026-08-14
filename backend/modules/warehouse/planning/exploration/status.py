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


class WarehouseExplorationStatusMixin:
    async def _emit_snapshot_status(self, orch: Orchestrator, snapshot: MapSnapshot) -> None:
        now = time.monotonic()
        if (now - self._last_snapshot_event_at) < float(self.map_snapshot_interval_s):
            return
        self._last_snapshot_event_at = now
        payload = {
            "state": self._state.value,
            "free_cells": int(snapshot.free_cells),
            "occupied_cells": int(snapshot.occupied_cells),
            "explored_cells": int(snapshot.explored_cells),
        }
        if getattr(orch, "mqtt", None):
            try:
                orch.mqtt.publish("drone/indoor_exploration/status", payload, qos=1)
            except Exception:
                logger.exception("Failed publishing indoor exploration status to MQTT")
        await self._add_event_safe(orch, "indoor_map_snapshot", payload)

    async def _transition(self, orch: Orchestrator, state: IndoorMissionState) -> None:
        self._state = state
        self._state_history.append(state)
        await self._publish_status(
            orch,
            {
                "state": state.value,
                "elapsed_s": round(self._flight_elapsed_s(), 2),
            },
        )

    async def _publish_status(self, orch: Orchestrator, payload: dict[str, object]) -> None:
        if getattr(orch, "mqtt", None):
            try:
                orch.mqtt.publish("drone/indoor_exploration/status", payload, qos=1)
            except Exception:
                logger.exception("Failed publishing indoor exploration status to MQTT")
