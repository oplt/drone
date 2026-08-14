from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from backend.modules.missions.schemas.mission_types import SIM_WAREHOUSE_LOCAL_ORIGIN
from backend.modules.vehicle_runtime.types import Coordinate
from backend.modules.warehouse.planning.local_planner import (
    WarehouseDockConfig,
    WarehouseLaneStrategy,
    WarehousePlanResult,
    WarehouseScanPattern,
    WarehouseViewMode,
)
from backend.modules.warehouse.planning.scan.capture import WarehouseScanCaptureMixin
from backend.modules.warehouse.planning.scan.diagnostics import WarehouseScanDiagnosticsMixin
from backend.modules.warehouse.planning.scan.fly_scan import WarehouseScanFlyScanMixin
from backend.modules.warehouse.planning.scan.fly_scan_complete import (
    WarehouseScanFlyScanCompleteMixin,
)
from backend.modules.warehouse.planning.scan.fly_scan_teardown import (
    WarehouseScanFlyScanTeardownMixin,
)
from backend.modules.warehouse.planning.scan.legs import WarehouseScanLegsMixin
from backend.modules.warehouse.planning.scan.live_map import WarehouseScanLiveMapMixin
from backend.modules.warehouse.planning.scan.persistence import WarehouseScanPersistenceMixin
from backend.modules.warehouse.planning.scan.perception import WarehouseScanPerceptionMixin
from backend.modules.warehouse.planning.scan.plan import WarehouseScanPlanMixin
from backend.modules.warehouse.service.runtime_safety import WarehouseRuntimeSafetyTracker

if TYPE_CHECKING:
    from backend.modules.vehicle_runtime.orchestrator import Orchestrator


@dataclass
class WarehouseScanMission(
    WarehouseScanFlyScanMixin,
    WarehouseScanFlyScanTeardownMixin,
    WarehouseScanFlyScanCompleteMixin,
    WarehouseScanPlanMixin,
    WarehouseScanLegsMixin,
    WarehouseScanLiveMapMixin,
    WarehouseScanDiagnosticsMixin,
    WarehouseScanPerceptionMixin,
    WarehouseScanCaptureMixin,
    WarehouseScanPersistenceMixin,
):
    """
    Indoor warehouse scan mission.

    Uses local ENU setpoints until the MAVLink adapter boundary.
    polygon_local_m defines the warehouse footprint in metres relative to the
    dock/takeoff origin.  The planner works entirely in that metric frame and
    produces EnuCoordinate setpoints converted only by the vehicle adapter.
    """

    # Local metric footprint — [[x_m, y_m], ...] from dock origin
    area_polygon_local_m: list[tuple[float, float]] | None = None
    dock_config: WarehouseDockConfig | None = None

    # Scan geometry — kept in sync with WarehouseMissionDefaults
    base_height_m: float = 4.0  # first layer height above floor (m)
    corridor_spacing_m: float = 2.0
    aisle_axis_deg: float | None = None
    clearance_m: float = 0.6
    perimeter_offset_m: float = 0.5
    scan_pattern: WarehouseScanPattern = "aisle_serpentine"
    lane_strategy: WarehouseLaneStrategy = "serpentine"
    view_mode: WarehouseViewMode = "forward"
    layer_count: int = 2
    layer_spacing_m: float = 1.2
    ceiling_height_m: float | None = 8.0
    ceiling_margin_m: float = 0.7

    # Flight behaviour — kept in sync with WarehouseMissionDefaults
    interpolate_steps_work_leg: int = 4
    interpolate_steps_transit_leg: int = 1
    scan_pause_s: float = 0.0
    work_speed_mps: float | None = 0.8
    transit_speed_mps: float | None = 1.4
    max_path_points: int = 3000

    # Capture / persistence
    mission_kind: str = "warehouse_scan"
    owner_id: int | None = None
    warehouse_map_id: int | None = None
    warehouse_name: str | None = None
    reference_mapping_job_id: int | None = None
    sensor_rig_id: int | None = None
    await_capture_sync: bool = True
    capture_sync_wait_timeout_s: float = 60.0
    capture_sync_poll_interval_s: float = 1.0
    capture_min_files: int = 1

    # Video
    enable_video_recording: bool = True
    video_recording_root: str = "backend/storage/drone_video"

    # Safety limits
    max_segments: int = 2500
    max_route_m: float = 15_000.0
    localization_confidence_min: float = 0.5

    _last_speed_mps: float | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _plan_cache: WarehousePlanResult | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _plan_cache_key: tuple[object, ...] | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _runtime_safety: WarehouseRuntimeSafetyTracker = field(
        default_factory=WarehouseRuntimeSafetyTracker,
        init=False,
        repr=False,
        compare=False,
    )
    _mapping_warmup_task: asyncio.Task | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    # ------------------------------------------------------------------
    # Preflight / plan
    # ------------------------------------------------------------------

    def get_waypoints(self) -> list[Coordinate]:
        # Warehouse scans are flown in the local metric frame, so there is no
        # GPS waypoint list to hand to the shared mission pipeline.
        return []

    def get_preflight_mission_data(self) -> dict[str, object]:
        plan, _ = self._build_plan()
        return {
            "type": "warehouse_scan",
            "waypoints": [],
            "polygon": [],
            "speed": float(self.work_speed_mps or 0.8),
            "altitude_agl": float(self.base_height_m),
            "local_origin": SIM_WAREHOUSE_LOCAL_ORIGIN.model_dump(mode="python"),
            "sensor_rig_id": self.sensor_rig_id,
            "dock_marker_id": self.dock_config.marker_id if self.dock_config else None,
            "dock_precision_required": (
                bool(self.dock_config.precision_required) if self.dock_config else False
            ),
            "control_mode": "local_setpoint",
            "local_control_mode": "local_setpoint",
            "base_height_m": float(self.base_height_m),
            "work_speed_mps": float(self.work_speed_mps or 0.8),
            "transit_speed_mps": float(self.transit_speed_mps or 1.4),
            "local_polygon": [
                {"x_m": float(x), "y_m": float(y), "z_m": 0.0} for x, y in plan.local_polygon
            ],
            "corridors": [
                {
                    "corridor_id": c.corridor_id,
                    "start": {
                        "x_m": float(c.start.x_m),
                        "y_m": float(c.start.y_m),
                        "z_m": float(c.start.z_m),
                    },
                    "end": {
                        "x_m": float(c.end.x_m),
                        "y_m": float(c.end.y_m),
                        "z_m": float(c.end.z_m),
                    },
                    "width_m": float(c.width_m),
                    "heading_deg": float(c.heading_deg),
                    "axis_deg": float(c.axis_deg),
                    "source": c.source,
                }
                for c in plan.corridors
            ],
            "obstacles_3d": [
                {
                    "obstacle_id": obstacle.obstacle_id,
                    "center": {
                        "x_m": float(obstacle.center.x_m),
                        "y_m": float(obstacle.center.y_m),
                        "z_m": float(obstacle.center.z_m),
                    },
                    "size_x_m": float(obstacle.size_x_m),
                    "size_y_m": float(obstacle.size_y_m),
                    "size_z_m": float(obstacle.size_z_m),
                }
                for obstacle in plan.obstacles_3d
            ],
            "keepout_zones": [
                {
                    "zone_id": zone.zone_id,
                    "footprint": [
                        {"x_m": float(x), "y_m": float(y), "z_m": 0.0} for x, y in zone.footprint
                    ],
                    "min_z_m": zone.min_z_m,
                    "max_z_m": zone.max_z_m,
                }
                for zone in plan.keepout_zones
            ],
            "scan_layers": [
                {
                    "layer_index": int(layer.layer_index),
                    "label": layer.label,
                    "z_m": float(layer.z_m),
                }
                for layer in plan.scan_layers
            ],
            "corridor_spacing_m": float(self.corridor_spacing_m),
            "aisle_axis_deg": self.aisle_axis_deg,
            "clearance_m": float(self.clearance_m),
            "perimeter_offset_m": float(self.perimeter_offset_m),
            "scan_pattern": self.scan_pattern,
            "lane_strategy": self.lane_strategy,
            "view_mode": self.view_mode,
            "layer_count": int(self.layer_count),
            "layer_spacing_m": float(self.layer_spacing_m),
            "ceiling_height_m": self.ceiling_height_m,
            "ceiling_margin_m": float(self.ceiling_margin_m),
            "interpolate_steps_work_leg": int(self.interpolate_steps_work_leg),
            "interpolate_steps_transit_leg": int(self.interpolate_steps_transit_leg),
        }

    # ------------------------------------------------------------------
    # Execution entry point
    # ------------------------------------------------------------------

    async def execute(self, orch: Orchestrator, *, alt: float = 4.0) -> None:
        # alt is passed by the orchestrator framework; we treat it as base_height_m
        if alt != self.base_height_m:
            self.base_height_m = float(alt)
            self._plan_cache = None
            self._plan_cache_key = None

        await orch.run_mission(
            self,
            alt=float(self.base_height_m),
            flight_fn=lambda: self.fly_scan(orch),
        )
