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


class WarehouseScanPlanMixin:
    def _plan_cache_fingerprint(self) -> tuple[object, ...]:
        dock = self.dock_config
        dock_key: tuple[object, ...] | None = None
        if dock is not None:
            dock_key = (
                dock.dock_pose,
                dock.entry_pose,
                dock.exit_pose,
                dock.marker_id,
                dock.dock_yaw_deg,
                bool(dock.precision_required),
            )
        return (
            tuple((float(x), float(y)) for x, y in (self.area_polygon_local_m or [])),
            float(self.base_height_m),
            float(self.corridor_spacing_m),
            self.aisle_axis_deg if self.aisle_axis_deg is None else float(self.aisle_axis_deg),
            float(self.clearance_m),
            float(self.perimeter_offset_m),
            self.scan_pattern,
            self.lane_strategy,
            self.view_mode,
            int(self.layer_count),
            float(self.layer_spacing_m),
            self.ceiling_height_m if self.ceiling_height_m is None else float(self.ceiling_height_m),
            float(self.ceiling_margin_m),
            int(self.max_segments),
            float(self.max_route_m),
            dock_key,
        )

    def _build_plan(self) -> tuple[WarehousePlanResult, float]:
        if not self.area_polygon_local_m:
            raise ValueError("WarehouseScanMission requires area_polygon_local_m.")

        cache_key = self._plan_cache_fingerprint()
        if self._plan_cache is not None and self._plan_cache_key == cache_key:
            route_m = float(self._plan_cache.stats.get("route_m", 0.0) or 0.0)
            return self._plan_cache, route_m

        plan = plan_warehouse_scan(
            polygon_local_m=list(self.area_polygon_local_m),
            base_height_m=float(self.base_height_m),
            corridor_spacing_m=float(self.corridor_spacing_m),
            aisle_axis_deg=self.aisle_axis_deg,
            clearance_m=float(self.clearance_m),
            perimeter_offset_m=float(self.perimeter_offset_m),
            scan_pattern=self.scan_pattern,
            lane_strategy=self.lane_strategy,
            view_mode=self.view_mode,
            layer_count=int(self.layer_count),
            layer_spacing_m=float(self.layer_spacing_m),
            ceiling_height_m=self.ceiling_height_m,
            ceiling_margin_m=float(self.ceiling_margin_m),
            max_waypoints=int(self.max_segments),
            max_route_m=float(self.max_route_m),
            dock_config=self.dock_config,
        )
        self._plan_cache = plan
        self._plan_cache_key = cache_key
        route_m = float(plan.stats.get("route_m", 0.0) or 0.0)
        return plan, route_m

    async def _plan_scan(self, orch: Orchestrator) -> None:
        plan, route_m = self._build_plan()
        self._plan_cache = plan
        await self._add_event_safe(
            orch,
            "warehouse_scan_planned",
            {
                "mission_kind": self.mission_kind,
                "aisle_axis_deg": float(plan.stats.get("aisle_axis_deg", 0.0) or 0.0),
                "corridors": int(plan.stats.get("corridors", 0) or 0),
                "layers": int(plan.stats.get("layers", 0) or 0),
                "segments": int(plan.stats.get("segments", 0) or 0),
                "route_m": round(route_m, 1),
                "scan_pattern": self.scan_pattern,
                "view_mode": self.view_mode,
                "lane_strategy": self.lane_strategy,
                "dock_planned": bool(plan.stats.get("dock_planned")),
                "dock_inferred": bool(plan.stats.get("dock_inferred")),
                "dock_marker_id": plan.stats.get("dock_marker_id"),
                "control_mode": "local_setpoint",
            },
        )
