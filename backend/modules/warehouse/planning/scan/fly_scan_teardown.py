from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.modules.vehicle_runtime.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class WarehouseScanFlyScanTeardownMixin:
    async def _fly_scan_teardown(
        self,
        orch: Orchestrator,
        *,
        airborne: bool,
        mission_error: Exception | None,
        video_recording_active: bool,
        perception_started: bool,
        capture_started: bool,
    ) -> Exception | None:
        if airborne:
            try:
                await self._add_event_safe(orch, "landing_command_sent", {})
                await orch.async_drone.land()
                await orch.async_drone.wait_until_disarmed(900)
                await self._add_event_safe(orch, "landed_dock", {})
            except Exception as exc:
                if mission_error is None:
                    mission_error = exc
                await self._add_event_safe(
                    orch,
                    "warehouse_scan_landing_failed",
                    {"error": str(exc)},
                )
                logger.exception("Warehouse scan landing failed")

        # Stop video immediately after landing; mapping/capture stop can take longer.
        video_stop_task = (
            asyncio.create_task(self._stop_video_recording(orch))
            if video_recording_active
            else None
        )

        if perception_started:
            from backend.modules.warehouse.service.colored_pointcloud_live_map_bridge import (
                drain_colored_pointcloud_live_map_bridge,
            )

            drained = await drain_colored_pointcloud_live_map_bridge(timeout_s=5.0)
            await self._add_event_safe(
                orch,
                "warehouse_scan_live_map_drain",
                {"drained": drained},
            )
            stop_result = await self._stop_perception_mapping(orch)
            from backend.modules.warehouse.service.capture_finalize import (
                resolve_capture_session_dir,
                wait_for_mapping_artifacts,
            )

            ros_session_dir = resolve_capture_session_dir(
                self._flight_token(orch),
                stop_data=stop_result.data if isinstance(stop_result.data, dict) else None,
            )
            export_ready = await wait_for_mapping_artifacts(ros_session_dir)
            await self._add_event_safe(
                orch,
                "warehouse_scan_artifact_export",
                {
                    "ready": export_ready,
                    "session_dir": str(ros_session_dir),
                    "has_mapping_artifacts": export_ready,
                },
            )

        if capture_started:
            await self._stop_capture_if_supported(orch)

        if video_stop_task is not None:
            await video_stop_task
        return mission_error
