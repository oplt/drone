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


class WarehouseScanLiveMapMixin:
    def _flight_token(self, orch: Orchestrator) -> str:
        return _safe_token(
            getattr(orch, "current_client_flight_id", None)
            or getattr(orch, "_flight_id", None)
            or "unknown"
        )

    async def _restart_live_map_publisher(
        self,
        flight_id: str,
        *,
        include_main_bridge: bool = True,
    ) -> None:
        """Stream odometry + RGB-D/nvblox colored layers; raw Mid360 is optional.

        The bridges are independent, so they are started concurrently instead of
        serially — that removed the ~9s serial start gap before first pixels.
        """
        from backend.modules.warehouse.service.colored_pointcloud_live_map_bridge import (
            start_colored_pointcloud_live_map_bridge,
        )
        from backend.modules.warehouse.service.live_map_bridge import (
            start_warehouse_live_map_bridge,
        )
        from backend.modules.warehouse.service.live_map_config import (
            persist_raw_lidar_layer,
            raw_lidar_enabled,
            should_persist_raw_lidar_chunks,
        )
        from backend.modules.warehouse.service.map_source_config import (
            WAREHOUSE_LIVE_MAP_SOURCES,
        )
        from backend.modules.warehouse.service.raw_pointcloud_live_map_bridge import (
            start_raw_pointcloud_live_map_bridge,
        )

        async def _start_main_bridge() -> None:
            try:
                await start_warehouse_live_map_bridge(flight_id)
                logger.info("Started warehouse live map bridge for flight_id=%s", flight_id)
            except Exception as exc:
                logger.warning("Could not start warehouse live map bridge: %s", exc)

        async def _start_colored_bridge() -> None:
            try:
                await start_colored_pointcloud_live_map_bridge(flight_id)
                logger.info(
                    "Started colored point-cloud live map bridge for flight_id=%s",
                    flight_id,
                )
            except Exception as exc:
                logger.warning("Could not start colored point-cloud live map bridge: %s", exc)

        async def _start_nvblox_bridge() -> None:
            try:
                from backend.modules.warehouse.service.nvblox_layers_live_map_bridge import (
                    start_nvblox_layers_live_map_bridge,
                )

                await start_nvblox_layers_live_map_bridge(flight_id)
                logger.info(
                    "Started nvblox layers live-map bridge for flight_id=%s",
                    flight_id,
                )
            except Exception as exc:
                logger.warning("Could not start nvblox layers live-map bridge: %s", exc)

        async def _start_raw_bridge() -> None:
            mid360 = WAREHOUSE_LIVE_MAP_SOURCES["mid360_raw"]
            try:
                await start_raw_pointcloud_live_map_bridge(
                    flight_id,
                    topic=mid360.topic,
                    global_frame=mid360.global_frame,
                    max_points=mid360.max_points,
                    min_publish_interval_s=mid360.min_publish_interval_s,
                    persist_to_disk=should_persist_raw_lidar_chunks(),
                )
                logger.info(
                    "Started warehouse raw point-cloud live map bridge for flight_id=%s persist=%s",
                    flight_id,
                    should_persist_raw_lidar_chunks(),
                )
            except Exception as exc:
                logger.warning("Could not start raw point-cloud live map bridge: %s", exc)

        starters = [_start_colored_bridge(), _start_nvblox_bridge()]
        if include_main_bridge:
            starters.insert(0, _start_main_bridge())

        if raw_lidar_enabled() or persist_raw_lidar_layer():
            starters.append(_start_raw_bridge())
        else:
            logger.info(
                "Skipping raw Mid360 live-map bridge for flight_id=%s "
                "(preview and persist disabled)",
                flight_id,
            )

        await asyncio.gather(*starters)
