from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from backend.db.models import FlightStatus
from backend.drone.models import Coordinate, LocalCoordinate
from backend.flight.missions.warehouse_local_planner import (
    WarehouseDockConfig,
    WarehouseLaneStrategy,
    WarehouseLocalPoint,
    WarehousePlanResult,
    WarehousePlanSegment,
    WarehouseScanPattern,
    WarehouseViewMode,
    plan_warehouse_scan,
)
from backend.services.warehouse.warehouse_capture import WarehouseCaptureSessionService
from backend.services.warehouse.warehouse_mapping import WarehouseScanMappingService
from backend.video.runtime import shared_video_runtime

if TYPE_CHECKING:
    from backend.drone.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

_UNSAFE_TOKEN_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_token(raw: object) -> str:
    token = _UNSAFE_TOKEN_CHARS.sub("_", str(raw or "")).strip("._-")
    return token or "unknown"


@dataclass(frozen=True)
class WarehouseExecutionFrame:
    """
    Offset between the planner's local origin (dock/polygon origin) and the
    drone's live NED frame measured at takeoff.  All values in metres.
    """

    north_offset_m: float
    east_offset_m: float
    down_offset_m: float


@dataclass
class WarehouseScanMission:
    """
    Indoor warehouse scan mission.

    Uses local NED setpoints throughout — no GPS, no lon/lat, no altitude AGL.
    polygon_local_m defines the warehouse footprint in metres relative to the
    dock/takeoff origin.  The planner works entirely in that metric frame and
    produces LocalCoordinate setpoints that are sent directly to the drone.
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
            "local_origin": {"alt_m": 0.0},
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

        await orch.run_mission(
            self,
            alt=float(self.base_height_m),
            flight_fn=lambda: self.fly_scan(orch),
        )

    # ------------------------------------------------------------------
    # Main flight coroutine
    # ------------------------------------------------------------------

    async def fly_scan(self, orch: Orchestrator) -> None:
        if not self.area_polygon_local_m:
            raise ValueError(
                "WarehouseScanMission requires area_polygon_local_m "
                "([[x_m, y_m], ...] in the dock-relative local frame)."
            )
        await self._plan_scan(orch)

        self._last_speed_mps = None
        plan, _ = self._build_plan()

        capture_session_service = WarehouseCaptureSessionService()
        mapping_service = WarehouseScanMappingService()
        session = capture_session_service.start_session(
            flight_id=getattr(orch, "_flight_id", "unknown")
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
        video_recording_active = False
        airborne = False
        mapping_saved = False
        execution_frame: WarehouseExecutionFrame | None = None

        try:
            await asyncio.sleep(0.5)
            await asyncio.to_thread(orch.drone.arm_and_takeoff, float(self.base_height_m))
            airborne = True
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
            if capture_started:
                await self._stop_capture_if_supported(orch)

            if airborne:
                try:
                    await asyncio.to_thread(orch.drone.land)
                    await self._add_event_safe(orch, "landing_command_sent", {})
                    await asyncio.to_thread(orch.drone.wait_until_disarmed, 900)
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

            # Stop video as soon as we're on the ground — mapping can take minutes
            if video_recording_active:
                await self._stop_video_recording(orch)

        if mission_error is None:
            try:
                capture_paths = await self._download_capture_if_supported(
                    orch,
                    destination_dir=str(session.session_dir),
                )
                imported_direct = await asyncio.to_thread(
                    capture_session_service.import_external_files,
                    session,
                    capture_paths=capture_paths,
                )
                await self._add_event_safe(
                    orch,
                    "warehouse_scan_direct_download",
                    {
                        "downloaded_paths_count": len(capture_paths),
                        "imported_count": imported_direct,
                    },
                )

                sync_trigger = await asyncio.to_thread(
                    capture_session_service.trigger_external_sync,
                    session,
                )
                await self._add_event_safe(orch, "warehouse_scan_external_sync", sync_trigger)

                sync_result = await asyncio.to_thread(
                    capture_session_service.finalize_session,
                    session,
                    min_files=self.capture_min_files if self.await_capture_sync else 0,
                    timeout_s=self.capture_sync_wait_timeout_s if self.await_capture_sync else 0.0,
                    poll_interval_s=self.capture_sync_poll_interval_s,
                    extra_meta={
                        "mission_kind": self.mission_kind,
                        "work_speed_mps": self.work_speed_mps,
                        "transit_speed_mps": self.transit_speed_mps,
                        "scan_pattern": self.scan_pattern,
                        "view_mode": self.view_mode,
                        "layer_count": self.layer_count,
                        "warehouse_map_id": self.warehouse_map_id,
                        "reference_mapping_job_id": self.reference_mapping_job_id,
                    },
                )
                await self._add_event_safe(
                    orch,
                    "warehouse_scan_capture_staged",
                    {
                        "source_dir": sync_result.get("source_dir"),
                        "file_count": sync_result.get("file_count", 0),
                        "status": sync_result.get("status"),
                    },
                )

                required_capture_files = max(1, int(self.capture_min_files))
                actual_capture_files = int(sync_result.get("file_count", 0) or 0)
                if actual_capture_files < required_capture_files:
                    raise RuntimeError(
                        "Warehouse scan capture is incomplete. "
                        f"Received {actual_capture_files} files; at least "
                        f"{required_capture_files} are required for 3D map persistence."
                    )

                if self.owner_id is None:
                    raise RuntimeError(
                        "Warehouse scan owner_id is required to persist captured warehouse maps."
                    )

                mapping_result = await mapping_service.persist_capture(
                    owner_id=int(self.owner_id),
                    warehouse_map_id=self.warehouse_map_id,
                    warehouse_name=self.warehouse_name,
                    polygon_local_m=list(self.area_polygon_local_m or []),
                    session_dir=session.session_dir,
                    capture_result=sync_result,
                    reference_mapping_job_id=self.reference_mapping_job_id,
                    flight_id=getattr(orch, "_flight_id", None),
                )
                mapping_saved = True
                await self._add_event_safe(orch, "warehouse_scan_mapping_saved", mapping_result)

            except Exception as exc:
                mapping_error = exc
                await self._add_event_safe(
                    orch,
                    "warehouse_scan_mapping_failed",
                    {"error": str(exc)},
                )
                logger.exception("Warehouse scan mapping persistence failed")
        else:
            await self._add_event_safe(
                orch,
                "warehouse_scan_mapping_skipped",
                {"reason": "flight_failed", "error": str(mission_error)},
            )

        final_status = FlightStatus.COMPLETED if mission_error is None else FlightStatus.FAILED
        if mission_error is not None:
            final_note = "Warehouse scan flight failed; 3D map persistence was skipped"
        elif mapping_saved:
            final_note = "Warehouse scan flight completed and 3D map persisted"
        elif mapping_error is not None:
            final_note = (
                "Warehouse scan flight completed but 3D map persistence failed: "
                + str(mapping_error)[:180]
            )
        else:
            final_note = "Warehouse scan flight completed"

        await self._finish_flight_safe(orch, status=final_status, note=final_note)

        await self._add_event_safe(
            orch,
            "warehouse_scan_complete",
            {
                "segments": len(plan.segments),
                "work_legs": sum(1 for s in plan.segments if s.work_leg),
                "route_m": round(float(plan.stats.get("route_m", 0.0) or 0.0), 1),
                "mapping_saved": mapping_saved,
                "mapping_error": str(mapping_error) if mapping_error is not None else None,
                "flight_status": final_status.value,
                "scan_pattern": self.scan_pattern,
                "view_mode": self.view_mode,
                "layers": int(self.layer_count),
            },
        )

        if mission_error is not None:
            raise mission_error

    # ------------------------------------------------------------------
    # Plan building
    # ------------------------------------------------------------------

    def _build_plan(self) -> tuple[WarehousePlanResult, float]:
        if self._plan_cache is not None:
            route_m = float(self._plan_cache.stats.get("route_m", 0.0) or 0.0)
            return self._plan_cache, route_m
        if not self.area_polygon_local_m:
            raise ValueError("WarehouseScanMission requires area_polygon_local_m.")

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

    # ------------------------------------------------------------------
    # Leg execution
    # ------------------------------------------------------------------

    async def _fly_leg(
        self,
        orch: Orchestrator,
        segment: WarehousePlanSegment,
        leg_index: int,
        total_legs: int,
        execution_frame: WarehouseExecutionFrame,
    ) -> None:
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
            await asyncio.to_thread(orch.drone.follow_local_setpoints, local_segment)
        except NotImplementedError as exc:
            raise RuntimeError(
                "The active drone adapter does not support local setpoint control "
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
        telemetry = await asyncio.to_thread(orch.drone.get_telemetry)
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

        frame = WarehouseExecutionFrame(
            north_offset_m=float(north) - float(dock_point.y_m),
            east_offset_m=float(east) - float(dock_point.x_m),
            down_offset_m=float(down) + float(dock_point.z_m),
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
                    "north_m": float(frame.north_offset_m),
                    "east_m": float(frame.east_offset_m),
                    "down_m": float(frame.down_offset_m),
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
    ) -> LocalCoordinate:
        return LocalCoordinate(
            north_m=float(point.y_m) + float(execution_frame.north_offset_m),
            east_m=float(point.x_m) + float(execution_frame.east_offset_m),
            down_m=(-float(point.z_m)) + float(execution_frame.down_offset_m),
            yaw_deg=yaw_deg,
        )

    def _interpolate_local_segment(
        self,
        a: LocalCoordinate,
        b: LocalCoordinate,
        *,
        steps: int,
    ) -> list[LocalCoordinate]:
        if steps <= 0:
            return [a, b]

        pts: list[LocalCoordinate] = []
        for i in range(steps + 2):
            t = i / (steps + 1)
            yaw_deg = (
                None
                if a.yaw_deg is None
                else float(a.yaw_deg) + ((float(b.yaw_deg or a.yaw_deg) - float(a.yaw_deg)) * t)
            )
            pts.append(
                LocalCoordinate(
                    north_m=(a.north_m + (b.north_m - a.north_m) * t),
                    east_m=(a.east_m + (b.east_m - a.east_m) * t),
                    down_m=(a.down_m + (b.down_m - a.down_m) * t),
                    yaw_deg=yaw_deg,
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
        if self._last_speed_mps is not None and math.isclose(
            float(self._last_speed_mps), float(speed_mps), abs_tol=1e-3
        ):
            return

        for name in ("set_speed", "set_groundspeed", "set_cruise_speed"):
            fn = getattr(orch.drone, name, None)
            if not callable(fn):
                continue
            try:
                await asyncio.to_thread(fn, float(speed_mps))
                self._last_speed_mps = float(speed_mps)
                return
            except TypeError:
                try:
                    await asyncio.to_thread(fn, speed_mps=float(speed_mps))
                    self._last_speed_mps = float(speed_mps)
                    return
                except Exception:
                    logger.debug("Speed setter %s rejected keyword form", name)
            except Exception:
                logger.debug("Speed setter %s failed", name)

    # ------------------------------------------------------------------
    # Capture hooks
    # ------------------------------------------------------------------

    async def _start_capture_if_supported(self, orch: Orchestrator) -> bool:
        for name in (
            "start_mapping_capture",
            "start_scan_capture",
            "start_lidar_capture",
        ):
            fn = getattr(orch.drone, name, None)
            if not callable(fn):
                continue
            try:
                await asyncio.to_thread(fn)
                await self._add_event_safe(
                    orch, "warehouse_scan_capture_started", {"handler": name}
                )
                return True
            except Exception:
                logger.exception("Failed to call optional capture start hook %s", name)
        return False

    async def _stop_capture_if_supported(self, orch: Orchestrator) -> None:
        for name in ("stop_mapping_capture", "stop_scan_capture", "stop_lidar_capture"):
            fn = getattr(orch.drone, name, None)
            if not callable(fn):
                continue
            try:
                await asyncio.to_thread(fn)
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
            fn = getattr(orch.drone, name, None)
            if not callable(fn):
                continue
            try:
                try:
                    result = await asyncio.to_thread(fn, destination_dir=destination_dir)
                except TypeError:
                    result = await asyncio.to_thread(fn, destination_dir)
                if isinstance(result, list):
                    downloaded.extend(str(item) for item in result)
            except Exception:
                logger.exception("Warehouse scan download hook %s failed", name)
        seen: set[str] = set()
        return [x for x in downloaded if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]

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
        try:
            drone_started = bool(await asyncio.to_thread(orch.drone.start_video_recording))
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
        try:
            drone_stopped = bool(await asyncio.to_thread(orch.drone.stop_video_recording))
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

    # ------------------------------------------------------------------
    # Flight DB helpers
    # ------------------------------------------------------------------

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
