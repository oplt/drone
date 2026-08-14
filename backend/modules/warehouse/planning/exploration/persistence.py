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


class WarehouseExplorationPersistenceMixin:
    async def _finish_flight_safe(
        self,
        orch: Orchestrator,
        *,
        status: FlightStatus,
        note: str,
    ) -> bool:
        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is None:
            return False
        safe_note = (note or "").strip()
        if len(safe_note) > 250:
            safe_note = safe_note[:247] + "..."
        try:
            await orch.repo.finish_flight(flight_id, status=status, note=safe_note)
            return True
        except Exception:
            logger.exception(
                "UnknownWarehouseExplorationMission: failed to finish flight_id=%s",
                flight_id,
            )
            return False

    async def _add_event_safe(
        self,
        orch: Orchestrator,
        event_type: str,
        data: dict | None = None,
    ) -> None:
        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is None:
            return
        try:
            await orch.repo.add_event(flight_id, event_type, data or {})
        except Exception:
            logger.exception(
                "UnknownWarehouseExplorationMission: failed to persist event '%s' (flight_id=%s)",
                event_type,
                flight_id,
            )
