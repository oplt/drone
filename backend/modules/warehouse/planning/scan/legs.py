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


class WarehouseScanLegsMixin:
    async def _fly_leg(
        self,
        orch: Orchestrator,
        segment: WarehousePlanSegment,
        leg_index: int,
        total_legs: int,
        execution_frame: WarehouseExecutionFrame,
    ) -> None:
        await self._check_runtime_safety(orch)
        work_leg = bool(segment.work_leg)
        leg_type = segment.leg_type
        yaw_deg = segment.yaw_deg
        speed = self.work_speed_mps if work_leg else self.transit_speed_mps
        await self._set_speed_if_supported(orch, speed)

        bounded_steps = self._bounded_steps(work_leg=work_leg, total_legs=total_legs)

        await self._add_event_safe(
            orch,
            "warehouse_scan_leg_started",
            {
                "leg_index": leg_index,
                "leg_type": leg_type,
                "work_leg": bool(work_leg),
                "points": bounded_steps + 2,
                "speed_mps": speed,
                "control_mode": "local_setpoint",
                "yaw_deg": yaw_deg,
                "from": {
                    "x_m": float(segment.local_start.x_m),
                    "y_m": float(segment.local_start.y_m),
                    "z_m": float(segment.local_start.z_m),
                },
                "to": {
                    "x_m": float(segment.local_end.x_m),
                    "y_m": float(segment.local_end.y_m),
                    "z_m": float(segment.local_end.z_m),
                },
            },
        )

        if orch.mqtt:
            try:
                orch.mqtt.publish(
                    "drone/warehouse_scan/status",
                    {
                        "leg_index": leg_index,
                        "leg_type": leg_type,
                        "work_leg": bool(work_leg),
                        "speed_mps": speed,
                        "control_mode": "local_setpoint",
                    },
                    qos=1,
                )
            except Exception:
                logger.exception("Failed to publish warehouse scan status to MQTT")

        local_segment = self._interpolate_local_segment(
            self._local_point_to_setpoint(
                segment.local_start, execution_frame=execution_frame, yaw_deg=yaw_deg
            ),
            self._local_point_to_setpoint(
                segment.local_end, execution_frame=execution_frame, yaw_deg=yaw_deg
            ),
            steps=bounded_steps,
        )

        try:
            await orch.async_drone.follow_enu_setpoints(local_segment)
        except NotImplementedError as exc:
            raise RuntimeError(
                "The active drone adapter does not support ENU local setpoint control "
                "required for warehouse scans."
            ) from exc

        if work_leg and self.scan_pause_s > 0:
            await asyncio.sleep(float(self.scan_pause_s))

        await self._add_event_safe(
            orch,
            "warehouse_scan_leg_completed",
            {"leg_index": leg_index, "leg_type": leg_type, "work_leg": bool(work_leg)},
        )

    def _bounded_steps(self, *, work_leg: bool, total_legs: int) -> int:
        requested = (
            int(self.interpolate_steps_work_leg)
            if work_leg
            else int(self.interpolate_steps_transit_leg)
        )
        max_steps_by_budget = max(0, (int(self.max_path_points) // max(1, total_legs)) - 2)
        return min(max(0, requested), max_steps_by_budget)

    # ------------------------------------------------------------------
    # Frame + setpoint helpers
    # ------------------------------------------------------------------

    async def _resolve_execution_frame(
        self,
        orch: Orchestrator,
        *,
        plan: WarehousePlanResult,
    ) -> WarehouseExecutionFrame:
        telemetry = await orch.async_drone.get_telemetry()
        north = getattr(telemetry, "local_north_m", None)
        east = getattr(telemetry, "local_east_m", None)
        down = getattr(telemetry, "local_down_m", None)
        if north is None or east is None or down is None:
            raise RuntimeError(
                "Warehouse mission start requires a live indoor local position; "
                "current telemetry has no local frame."
            )

        dock_point = plan.dock_point
        if dock_point is None:
            if not plan.segments:
                raise RuntimeError("Warehouse plan is empty; no dock anchor is available.")
            dock_point = plan.segments[0].local_start

        vehicle_enu = local_ned_position_to_enu(
            north_m=float(north), east_m=float(east), down_m=float(down)
        )
        frame = WarehouseExecutionFrame(
            x_offset_m=vehicle_enu.x_m - float(dock_point.x_m),
            y_offset_m=vehicle_enu.y_m - float(dock_point.y_m),
            z_offset_m=vehicle_enu.z_m - float(dock_point.z_m),
        )
        await self._add_event_safe(
            orch,
            "warehouse_scan_execution_frame_locked",
            {
                "dock_point_local": {
                    "x_m": float(dock_point.x_m),
                    "y_m": float(dock_point.y_m),
                    "z_m": float(dock_point.z_m),
                },
                "vehicle_local": {
                    "north_m": float(north),
                    "east_m": float(east),
                    "down_m": float(down),
                },
                "offset": {
                    "x_m": float(frame.x_offset_m),
                    "y_m": float(frame.y_offset_m),
                    "z_m": float(frame.z_offset_m),
                    "frame_id": "odom",
                },
            },
        )
        return frame

    def _local_point_to_setpoint(
        self,
        point: WarehouseLocalPoint,
        *,
        execution_frame: WarehouseExecutionFrame,
        yaw_deg: float | None,
    ) -> EnuCoordinate:
        return EnuCoordinate(
            x_m=float(point.x_m) + float(execution_frame.x_offset_m),
            y_m=float(point.y_m) + float(execution_frame.y_offset_m),
            z_m=float(point.z_m) + float(execution_frame.z_offset_m),
            yaw_rad=math.radians(float(yaw_deg)) if yaw_deg is not None else None,
        )

    def _interpolate_local_segment(
        self,
        a: EnuCoordinate,
        b: EnuCoordinate,
        *,
        steps: int,
    ) -> list[EnuCoordinate]:
        if steps <= 0:
            return [a, b]

        pts: list[EnuCoordinate] = []
        for i in range(steps + 2):
            t = i / (steps + 1)
            yaw_rad = (
                math.radians(
                    _interpolate_yaw_deg(
                        math.degrees(a.yaw_rad) if a.yaw_rad is not None else None,
                        math.degrees(b.yaw_rad) if b.yaw_rad is not None else None,
                        t,
                    )
                )
                if a.yaw_rad is not None or b.yaw_rad is not None
                else None
            )
            pts.append(
                EnuCoordinate(
                    x_m=(a.x_m + (b.x_m - a.x_m) * t),
                    y_m=(a.y_m + (b.y_m - a.y_m) * t),
                    z_m=(a.z_m + (b.z_m - a.z_m) * t),
                    yaw_rad=yaw_rad,
                )
            )
        return pts

    # ------------------------------------------------------------------
    # Speed helper
    # ------------------------------------------------------------------

    async def _set_speed_if_supported(
        self,
        orch: Orchestrator,
        speed_mps: float | None,
    ) -> None:
        if speed_mps is None:
            return
        speed = float(speed_mps)
        if self._last_speed_mps is not None and math.isclose(
            float(self._last_speed_mps), speed, abs_tol=1e-3
        ):
            return

        attempted: list[str] = []
        last_error: Exception | None = None
        for name in ("set_speed", "set_groundspeed", "set_cruise_speed"):
            fn = getattr(orch.drone, name, None)
            if not callable(fn):
                continue
            attempted.append(name)
            try:
                await asyncio.to_thread(fn, speed)
                self._last_speed_mps = speed
                return
            except TypeError as exc:
                last_error = exc
                try:
                    await asyncio.to_thread(fn, speed_mps=speed)
                    self._last_speed_mps = speed
                    return
                except TypeError as keyword_exc:
                    last_error = keyword_exc
                    logger.debug("Speed setter %s did not accept positional or keyword speed", name)
                except Exception as keyword_exc:
                    last_error = keyword_exc
                    logger.debug("Speed setter %s failed with keyword speed", name, exc_info=True)
            except Exception as exc:
                last_error = exc
                logger.debug("Speed setter %s failed", name, exc_info=True)

        if attempted:
            logger.warning(
                "All warehouse scan speed setters failed; continuing with previous/default speed attempted=%s error=%s",
                attempted,
                last_error,
            )
