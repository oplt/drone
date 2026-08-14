from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from backend.core.config.runtime import settings
from backend.modules.warehouse.planning.scan_geometry import (
    WarehouseExecutionFrame,
    active_mapping_startup_timing,
    angle_delta_deg as _angle_delta_deg,
    begin_mapping_startup_timing as _begin_mapping_startup_timing,
    dedupe_preserving_order as _dedupe_preserving_order,
    interpolate_yaw_deg as _interpolate_yaw_deg,
    normalize_angle_deg as _normalize_angle_deg,
    note_mapping_startup as _note_mapping_startup,
    safe_token_value as _safe_token,
)
from backend.infrastructure.runtime.blocking import run_blocking
from backend.infrastructure.camera.runtime import shared_video_runtime
from backend.infrastructure.vehicle.frame_conversion import local_ned_position_to_enu
from backend.modules.missions.flight_models import FlightStatus
from backend.modules.missions.schemas.mission_types import SIM_WAREHOUSE_LOCAL_ORIGIN
from backend.modules.vehicle_runtime.types import Coordinate, EnuCoordinate
from backend.modules.warehouse.exceptions import WarehouseMissionFailure
from backend.modules.warehouse.planning.local_planner import (
    WarehouseDockConfig,
    WarehouseLaneStrategy,
    WarehouseLocalPoint,
    WarehousePlanResult,
    WarehousePlanSegment,
    WarehouseScanPattern,
    WarehouseViewMode,
    plan_warehouse_scan,
)
from backend.modules.warehouse.ports import (
    WarehouseMappingStartRequest,
    WarehousePerceptionCommandResult,
    WarehousePerceptionPort,
)
from backend.modules.warehouse.service.bridge_flow import resolve_warehouse_bridge_flow
from backend.modules.warehouse.service.capture import WarehouseCaptureSessionService
from backend.modules.warehouse.service.mapping import WarehouseScanMappingService
from backend.modules.warehouse.service.runtime_safety import WarehouseRuntimeSafetyTracker
from backend.modules.warehouse.service.video import (
    warehouse_video_recording_enabled,
    warehouse_video_skip_reason,
)

if TYPE_CHECKING:
    from backend.modules.vehicle_runtime.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class WarehouseScanPersistenceMixin:
    async def _mark_mission_runtime_terminal_safe(
        self,
        orch: Orchestrator,
        *,
        mission_error: Exception | None,
        mapping_error: Exception | None,
        mapping_saved: bool,
    ) -> None:
        """Persist mission-runtime terminal state before best-effort cleanup."""
        client_flight_id = getattr(orch, "current_client_flight_id", None)
        if not client_flight_id:
            return

        from backend.modules.missions.application import mission_application
        from backend.modules.warehouse.exceptions import WarehouseMissionFailure

        if mission_error is None and mapping_error is None:
            return

        if (
            mission_error is None
            and isinstance(mapping_error, WarehouseMissionFailure)
            and mapping_error.stage == "capture"
            and mapping_error.action == "complete"
        ):
            state = "completed"
            error = str(mapping_error.message or mapping_error)[:500]
        elif mission_error is not None:
            state = "failed"
            error = str(mission_error)[:500]
        else:
            state = "failed"
            error = str(mapping_error)[:500] if mapping_error is not None else None

        try:
            db_row = await mission_application.get_by_client_id(str(client_flight_id))
            if db_row is not None and db_row.state in {"aborted", "completed", "failed"}:
                return
            await mission_application.set_state(
                str(client_flight_id),
                state=state,
                error=error,
            )
        except Exception:
            logger.warning(
                "Failed to mark mission runtime %s before cleanup (mapping_saved=%s)",
                client_flight_id,
                mapping_saved,
                exc_info=True,
            )

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
            logger.exception("WarehouseScanMission: failed to finish flight_id=%s", flight_id)
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
                "WarehouseScanMission: failed to persist event '%s' (flight_id=%s)",
                event_type,
                flight_id,
            )
