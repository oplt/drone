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


class WarehouseScanPerceptionMixin:
    def _perception_metadata(self, orch: Orchestrator, *, session_dir: Path) -> dict[str, object]:
        del orch
        return {
            "mission_kind": self.mission_kind,
            "warehouse_map_id": self.warehouse_map_id,
            "warehouse_name": self.warehouse_name,
            "sensor_rig_id": self.sensor_rig_id,
            "reference_mapping_job_id": self.reference_mapping_job_id,
            "scan_pattern": self.scan_pattern,
            "view_mode": self.view_mode,
            "layer_count": int(self.layer_count),
            "work_speed_mps": self.work_speed_mps,
            "transit_speed_mps": self.transit_speed_mps,
            "session_dir": str(session_dir),
            "polygon_local_m": [
                [float(x), float(y)] for x, y in (self.area_polygon_local_m or [])
            ],
        }

    async def _warm_mapping_stack_background(
        self,
        orch: Orchestrator,
        *,
        flight_id: str,
        session_dir: Path,
        startup_t0: float,
    ) -> None:
        from backend.modules.warehouse.service.live_map_readiness import (
            probe_mapping_tf_degraded,
            wait_for_rgbd_mapping_topics,
        )
        from backend.modules.warehouse.service.live_map_bridge import (
            start_warehouse_live_map_bridge,
        )
        warmup_timeout = settings.warehouse_mapping_warmup_rgbd_timeout_s
        t_wait = time.monotonic()
        try:
            await start_warehouse_live_map_bridge(flight_id)
            tf_deadline = time.monotonic() + max(
                1.0,
                float(settings.warehouse_preflight_tf_wait_s),
            )
            tf_status = await probe_mapping_tf_degraded()
            while tf_status.get("degraded") and time.monotonic() < tf_deadline:
                await asyncio.sleep(0.5)
                tf_status = await probe_mapping_tf_degraded()
            if tf_status.get("degraded"):
                logger.warning(
                    "Mapping TF degraded before bridge attach flight_id=%s detail=%s",
                    flight_id,
                    tf_status.get("detail"),
                )

            await self._restart_live_map_publisher(
                flight_id,
                include_main_bridge=False,
            )
            _note_mapping_startup("bridges_started_monotonic")

            rgbd_readiness = await wait_for_rgbd_mapping_topics(timeout_s=warmup_timeout)
            _note_mapping_startup("rgbd_ready_monotonic")
            await self._add_event_safe(
                orch,
                "warehouse_scan_mapping_warming",
                {
                    "phase": "rgbd_wait_complete",
                    "mapping_readiness": rgbd_readiness.to_dict(),
                    "tf_status": tf_status,
                    "warming_ms": int((time.monotonic() - t_wait) * 1000),
                },
            )

            port = build_warehouse_perception_port()
            bridge_flow = resolve_warehouse_bridge_flow()
            request = WarehouseMappingStartRequest(
                flight_id=flight_id,
                warehouse_map_id=self.warehouse_map_id,
                sensor_rig_id=self.sensor_rig_id,
                profile=bridge_flow.ros_profile,
                bridge_flow=bridge_flow.name,
                metadata=self._perception_metadata(orch, session_dir=session_dir),
            )
            result = await port.start_mapping(request)
            _note_mapping_startup("mapping_started_monotonic")

            extra_data: dict[str, object] = dict(result.data or {})
            extra_data["mapping_status"] = (
                "ready" if rgbd_readiness.ready and result.accepted else "degraded"
            )
            extra_data["rgbd_ready"] = rgbd_readiness.ready
            timing = _active_mapping_startup_timing()
            startup_timing: dict[str, object] = {
                "background_warmup_ms": int((time.monotonic() - startup_t0) * 1000),
                "mapping_readiness": rgbd_readiness.to_dict(),
            }
            if timing is not None:
                startup_timing.update(timing.as_dict())
            if rgbd_readiness.timing_ms:
                startup_timing.update(rgbd_readiness.timing_ms)

            await self._add_event_safe(
                orch,
                "warehouse_scan_perception_mapping_started",
                {
                    "accepted": result.accepted,
                    "status": result.status,
                    "detail": result.detail,
                    "data": extra_data,
                    "startup_timing_ms": startup_timing,
                },
            )
            if not result.accepted:
                logger.warning(
                    "Background mapping attach not accepted flight_id=%s status=%s",
                    flight_id,
                    result.status,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "Background mapping warmup failed flight_id=%s after %.1fs",
                flight_id,
                time.monotonic() - t_wait,
            )
            await self._add_event_safe(
                orch,
                "warehouse_scan_mapping_warmup_failed",
                {"flight_id": flight_id, "detail": str(exc)},
            )

    async def _start_perception_mapping(
        self,
        orch: Orchestrator,
        *,
        session_dir: Path,
        startup_t0: float | None = None,
    ) -> tuple[WarehousePerceptionCommandResult, object, dict[str, object]]:
        from backend.modules.warehouse.service.mapping_stack_lifecycle import (
            prepare_warehouse_scan_ros,
        )

        t0 = startup_t0 if startup_t0 is not None else time.monotonic()
        require_nvblox_ready = bool(
            getattr(settings, "warehouse_scan_require_nvblox_ready", True)
            or getattr(settings, "warehouse_preflight_wait_nvblox", False)
        )
        nvblox_timeout_s = (
            float(getattr(settings, "warehouse_flight_mapping_wait_s", 45.0))
            if require_nvblox_ready
            else 0.0
        )
        stack_status, flight_readiness, takeoff_ready, rgbd_readiness = (
            await prepare_warehouse_scan_ros(
                require_nvblox=require_nvblox_ready,
                sensor_timeout_s=30.0,
                nvblox_timeout_s=nvblox_timeout_s,
                wait_for_rgbd=True,
            )
        )
        t_prepared = time.monotonic()
        if not stack_status.running:
            logger.warning(
                "Mapping stack not fully running before takeoff; warming in background"
            )
        if not flight_readiness.bridge_reachable:
            raise WarehouseMissionFailure(
                reason="warehouse_bridge_unreachable",
                action="abort",
                stage="flight",
                message=flight_readiness.detail
                or "Warehouse ROS bridge could not be reached after starting nvblox",
                details=flight_readiness.to_dict(),
            )
        if not takeoff_ready.ready:
            raise WarehouseMissionFailure(
                reason="takeoff_sensors_not_ready",
                action="abort",
                stage="takeoff",
                message=takeoff_ready.detail
                or "Warehouse sensors not ready for takeoff",
                details=takeoff_ready.to_dict(),
            )
        if require_nvblox_ready and not flight_readiness.nvblox_ready:
            raise WarehouseMissionFailure(
                reason="nvblox_not_ready",
                action="abort",
                stage="takeoff",
                message=(
                    flight_readiness.detail
                    or "Nvblox ESDF/costmap did not become ready before takeoff."
                ),
                details=flight_readiness.to_dict(),
            )
        if not flight_readiness.core_ready:
            logger.warning(
                "Warehouse mapping sensors not fully ready before takeoff; "
                "continuing with background warmup detail=%s",
                flight_readiness.detail,
            )

        flight_id = self._flight_token(orch)
        os.environ["WAREHOUSE_ACTIVE_FLIGHT_ID"] = str(flight_id)
        await self._add_event_safe(
            orch,
            "warehouse_scan_mapping_warming",
            {
                "phase": "deferred_until_after_takeoff",
                "mapping_status": "warming_up",
                "mapping_readiness": rgbd_readiness.to_dict(),
            },
        )

        warmup_task = asyncio.create_task(
            self._warm_mapping_stack_background(
                orch,
                flight_id=flight_id,
                session_dir=session_dir,
                startup_t0=t0,
            ),
            name=f"warehouse-mapping-warmup-{flight_id}",
        )
        self._mapping_warmup_task = warmup_task
        warmup_task.add_done_callback(
            lambda _task: setattr(self, "_mapping_warmup_task", None)
        )

        extra_data: dict[str, object] = {
            "stack_pid": stack_status.pid,
            "nvblox_ready": flight_readiness.nvblox_ready,
            "rgbd_ready": rgbd_readiness.ready,
            "mapping_status": "warming_up",
        }
        if not flight_readiness.nvblox_ready:
            extra_data["nvblox_warning"] = (
                "Nvblox still warming; map outputs may appear during the scan"
            )

        timing = _active_mapping_startup_timing()
        startup_timing: dict[str, object] = {
            "prepare_ros_ms": int((t_prepared - t0) * 1000),
            "deferred_rgbd_warmup": True,
            "mapping_readiness": rgbd_readiness.to_dict(),
        }
        if timing is not None:
            startup_timing.update(timing.as_dict())

        merged = WarehousePerceptionCommandResult(
            accepted=True,
            status="warming_up",
            detail="Mapping stack warming in background; takeoff proceeding",
            data=extra_data,
        )
        return merged, takeoff_ready, startup_timing

    async def _stop_perception_mapping(
        self,
        orch: Orchestrator,
    ) -> WarehousePerceptionCommandResult:
        warmup_task = self._mapping_warmup_task
        if warmup_task is not None and not warmup_task.done():
            warmup_task.cancel()
            with suppress(asyncio.CancelledError):
                await warmup_task
        self._mapping_warmup_task = None

        port = build_warehouse_perception_port()
        try:
            result = await port.stop_mapping(flight_id=self._flight_token(orch))
        except Exception as exc:
            logger.exception("Warehouse perception stop failed")
            result = WarehousePerceptionCommandResult(
                accepted=False,
                status="failed",
                detail=str(exc),
            )
        await self._add_event_safe(
            orch,
            "warehouse_scan_perception_mapping_stopped",
            {
                "accepted": result.accepted,
                "status": result.status,
                "detail": result.detail,
                "data": result.data,
            },
        )
        return result

    async def _download_perception_artifacts(
        self,
        orch: Orchestrator,
        *,
        destination_dir: Path,
    ) -> list[str]:
        port = build_warehouse_perception_port()
        try:
            paths = await port.download_artifacts(
                flight_id=self._flight_token(orch),
                destination_dir=destination_dir,
            )
        except Exception:
            logger.exception("Warehouse perception artifact download failed")
            paths = []
        await self._add_event_safe(
            orch,
            "warehouse_scan_perception_artifacts_downloaded",
            {"downloaded_paths_count": len(paths), "destination_dir": str(destination_dir)},
        )
        return [str(path) for path in paths]
