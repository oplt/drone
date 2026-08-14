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


class WarehouseScanFlyScanMixin:
    async def fly_scan(self, orch: Orchestrator) -> None:
        if not self.area_polygon_local_m:
            raise ValueError(
                "WarehouseScanMission requires area_polygon_local_m "
                "([[x_m, y_m], ...] in the dock-relative local frame)."
            )
        flight_id = self._flight_token(orch)
        os.environ["WAREHOUSE_ACTIVE_FLIGHT_ID"] = str(flight_id)
        await self._plan_scan(orch)

        self._last_speed_mps = None
        plan, _ = self._build_plan()

        capture_session_service = await run_blocking(
            WarehouseCaptureSessionService,
            boundary="filesystem",
            operation="warehouse_capture_service_init",
            timeout_s=30.0,
        )
        mapping_service = WarehouseScanMappingService()
        session = await capture_session_service.start_session_async(
            flight_id=getattr(orch, "_flight_id", "unknown"),
        )
        await self._add_event_safe(
            orch,
            "warehouse_scan_capture_session_started",
            {
                "source_dir": session.relative_source_dir,
                "absolute_dir": str(session.session_dir),
            },
        )

        plan_segments = list(plan.segments)
        total_legs = max(1, len(plan_segments))

        mission_error: Exception | None = None
        mapping_error: Exception | None = None
        capture_started = False
        perception_started = False
        video_recording_active = False
        airborne = False
        mapping_saved = False
        execution_frame: WarehouseExecutionFrame | None = None

        try:
            startup_t0 = time.monotonic()
            _begin_mapping_startup_timing(mission_start_monotonic=startup_t0)
            perception_start, takeoff_ready, startup_timing = await self._start_perception_mapping(
                orch,
                session_dir=session.session_dir,
                startup_t0=startup_t0,
            )
            perception_started = bool(perception_start.accepted)
            if not takeoff_ready.ready:
                raise WarehouseMissionFailure(
                    reason="takeoff_sensors_not_ready",
                    action="abort",
                    stage="takeoff",
                    message=takeoff_ready.detail or "Warehouse sensors not ready for takeoff",
                    details=takeoff_ready.to_dict(),
                )
            _note_mapping_startup("preflight_pass_monotonic")
            await self._add_event_safe(
                orch,
                "warehouse_scan_takeoff_readiness",
                takeoff_ready.to_dict(),
            )
            if not perception_start.data.get("nvblox_ready") and perception_start.data.get(
                "nvblox_warning"
            ):
                await self._add_event_safe(
                    orch,
                    "warehouse_scan_nvblox_warming",
                    {"detail": perception_start.data.get("nvblox_warning")},
                )

            await self._add_event_safe(
                orch,
                "warehouse_scan_startup_timing",
                startup_timing,
            )

            await orch.async_drone.arm_and_takeoff(float(self.base_height_m))
            airborne = True
            self._runtime_safety.reset_for_takeoff()
            await self._add_event_safe(
                orch,
                "warehouse_scan_takeoff",
                {"base_height_m": float(self.base_height_m)},
            )

            video_recording_result = await self._start_video_recording(orch)
            video_recording_active = bool(
                video_recording_result.get("recording")
                or video_recording_result.get("drone_capture_started")
            )
            capture_started = await self._start_capture_if_supported(orch)
            execution_frame = await self._resolve_execution_frame(orch, plan=plan)

            for idx, segment in enumerate(plan_segments):
                await self._fly_leg(
                    orch=orch,
                    segment=segment,
                    leg_index=idx,
                    total_legs=total_legs,
                    execution_frame=execution_frame,
                )

        except Exception as exc:
            mission_error = exc
            await self._add_event_safe(
                orch,
                "warehouse_scan_path_failed",
                {"error": str(exc)},
            )
            logger.exception("Warehouse scan path failed")

        finally:
            mission_error = await self._fly_scan_teardown(
                orch,
                airborne=airborne,
                mission_error=mission_error,
                video_recording_active=video_recording_active,
                perception_started=perception_started,
                capture_started=capture_started,
            )

        mapping_saved, mapping_error = await self._fly_scan_persist_and_complete(
            orch,
            session=session,
            plan=plan,
            mission_error=mission_error,
            capture_session_service=capture_session_service,
            mapping_service=mapping_service,
            video_recording_active=video_recording_active,
        )
