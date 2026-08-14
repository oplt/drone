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


class WarehouseScanCaptureMixin:
    async def _start_capture_if_supported(self, orch: Orchestrator) -> bool:
        for name in (
            "start_mapping_capture",
            "start_scan_capture",
            "start_lidar_capture",
        ):
            if not callable(getattr(orch.drone, name, None)):
                continue
            try:
                await orch.async_drone.optional_call(name)
                await self._add_event_safe(
                    orch, "warehouse_scan_capture_started", {"handler": name}
                )
                return True
            except Exception:
                logger.exception("Failed to call optional capture start hook %s", name)
        return False

    async def _stop_capture_if_supported(self, orch: Orchestrator) -> None:
        for name in ("stop_mapping_capture", "stop_scan_capture", "stop_lidar_capture"):
            if not callable(getattr(orch.drone, name, None)):
                continue
            try:
                await orch.async_drone.optional_call(name)
                await self._add_event_safe(
                    orch, "warehouse_scan_capture_stopped", {"handler": name}
                )
                return
            except Exception:
                logger.exception("Failed to call optional capture stop hook %s", name)

    async def _download_capture_if_supported(
        self,
        orch: Orchestrator,
        *,
        destination_dir: str,
    ) -> list[str]:
        downloaded: list[str] = []
        for name in (
            "download_mapping_capture",
            "download_lidar_capture",
            "download_scan_capture",
        ):
            if not callable(getattr(orch.drone, name, None)):
                continue
            try:
                try:
                    result = await orch.async_drone.optional_call(
                        name, destination_dir=destination_dir
                    )
                except TypeError:
                    result = await orch.async_drone.optional_call(name, destination_dir)
                if isinstance(result, list):
                    downloaded.extend(str(item) for item in result)
            except Exception:
                logger.exception("Warehouse scan download hook %s failed", name)
        return _dedupe_preserving_order(downloaded)

    # ------------------------------------------------------------------
    # Video recording
    # ------------------------------------------------------------------

    def _video_recording_dir(self, *, flight_id: object) -> Path:
        root = Path(self.video_recording_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root / f"flight_{_safe_token(flight_id)}"

    async def _start_video_recording(self, orch: Orchestrator) -> dict[str, object]:
        if not self.enable_video_recording:
            return {"enabled": False}

        skip_reason = warehouse_video_skip_reason()
        if skip_reason or not warehouse_video_recording_enabled():
            payload = {
                "enabled": True,
                "recording": False,
                "skipped": True,
                "reason": skip_reason or "warehouse video source not configured for profile",
            }
            await self._add_event_safe(orch, "warehouse_scan_video_recording_started", payload)
            logger.info("Warehouse video recording skipped: %s", payload["reason"])
            return payload

        flight_id = (
            getattr(orch, "_flight_id", None)
            or getattr(orch, "current_client_flight_id", None)
            or "unknown"
        )
        recording_dir = self._video_recording_dir(flight_id=flight_id)
        recording_dir.mkdir(parents=True, exist_ok=True)

        backend_result: dict[str, object]
        try:
            backend_result = await shared_video_runtime.start_recording(
                recording_path=str(recording_dir)
            )
        except Exception as exc:
            backend_result = {
                "recording": False,
                "recording_file": None,
                "error": str(exc),
            }
            logger.exception("Failed to start backend warehouse video recording")

        drone_started = False
        if callable(getattr(orch.drone, "start_video_recording", None)):
            try:
                drone_started = await orch.async_drone.start_video_recording()
            except Exception:
                logger.exception("Failed to trigger drone-side video recording hook")

        payload = {
            "enabled": True,
            "recording": bool(backend_result.get("recording")),
            "recording_file": backend_result.get("recording_file"),
            "drone_capture_started": drone_started,
        }
        if backend_result.get("error"):
            payload["error"] = backend_result["error"]
        await self._add_event_safe(orch, "warehouse_scan_video_recording_started", payload)
        return payload

    async def _stop_video_recording(self, orch: Orchestrator) -> dict[str, object]:
        backend_result: dict[str, object]
        try:
            backend_result = await shared_video_runtime.stop_recording()
        except Exception as exc:
            backend_result = {"recording": False, "error": str(exc)}
            logger.exception("Failed to stop backend warehouse video recording")

        drone_stopped = False
        if callable(getattr(orch.drone, "stop_video_recording", None)):
            try:
                drone_stopped = await orch.async_drone.stop_video_recording()
            except Exception:
                logger.exception("Failed to stop drone-side video recording hook")

        payload = {
            "recording": bool(backend_result.get("recording")),
            "recording_file": backend_result.get("recording_file"),
            "drone_capture_stopped": drone_stopped,
        }
        if backend_result.get("error"):
            payload["error"] = backend_result["error"]
        await self._add_event_safe(orch, "warehouse_scan_video_recording_stopped", payload)
        return payload
