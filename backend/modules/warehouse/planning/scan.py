from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from backend.core.config.runtime import settings
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

_UNSAFE_TOKEN_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")
_warned_missing_startup_timing = False


def _safe_token(raw: object) -> str:
    token = _UNSAFE_TOKEN_CHARS.sub("_", str(raw or "")).strip("._-")
    return token or "unknown"


def _normalize_angle_deg(value: float) -> float:
    normalized = float(value) % 360.0
    if normalized > 180.0:
        normalized -= 360.0
    return normalized


def _angle_delta_deg(start_deg: float, end_deg: float) -> float:
    return _normalize_angle_deg(float(end_deg) - float(start_deg))


def _interpolate_yaw_deg(start_deg: float | None, end_deg: float | None, t: float) -> float | None:
    if start_deg is None and end_deg is None:
        return None
    if start_deg is None:
        return _normalize_angle_deg(float(end_deg))  # type: ignore[arg-type]
    if end_deg is None:
        return _normalize_angle_deg(float(start_deg))
    return _normalize_angle_deg(float(start_deg) + (_angle_delta_deg(float(start_deg), float(end_deg)) * float(t)))


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def build_warehouse_perception_port() -> WarehousePerceptionPort:
    from backend.infrastructure.warehouse.perception import build_warehouse_perception_port

    return build_warehouse_perception_port()


def _begin_mapping_startup_timing(*, mission_start_monotonic: float) -> None:
    global _warned_missing_startup_timing
    try:
        from backend.modules.warehouse.service.mapping_startup_timing import (
            begin_mapping_startup_timing,
        )

        begin_mapping_startup_timing(mission_start_monotonic=mission_start_monotonic)
    except ModuleNotFoundError as exc:
        if not _warned_missing_startup_timing:
            logger.warning("Optional mapping startup timing unavailable: %s", exc)
            _warned_missing_startup_timing = True


def _note_mapping_startup(mark: str) -> None:
    global _warned_missing_startup_timing
    try:
        from backend.modules.warehouse.service.mapping_startup_timing import (
            note_mapping_startup,
        )

        note_mapping_startup(mark)
    except ModuleNotFoundError as exc:
        if not _warned_missing_startup_timing:
            logger.warning("Optional mapping startup timing unavailable: %s", exc)
            _warned_missing_startup_timing = True


def _active_mapping_startup_timing():
    try:
        from backend.modules.warehouse.service.mapping_startup_timing import (
            active_mapping_startup_timing,
        )

        return active_mapping_startup_timing()
    except ModuleNotFoundError:
        return None


@dataclass(frozen=True)
class WarehouseExecutionFrame:
    """
    ENU offset between the planner origin and live odom measured at takeoff.
    """

    x_offset_m: float
    y_offset_m: float
    z_offset_m: float


@dataclass
class WarehouseScanMission:
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

    # ------------------------------------------------------------------
    # Main flight coroutine
    # ------------------------------------------------------------------

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

            await asyncio.to_thread(orch.drone.arm_and_takeoff, float(self.base_height_m))
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
            if airborne:
                try:
                    await self._add_event_safe(orch, "landing_command_sent", {})
                    await asyncio.to_thread(orch.drone.land)
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

        if mission_error is None:
            try:
                perception_paths = await self._download_perception_artifacts(
                    orch,
                    destination_dir=session.session_dir,
                )
                fallback_paths = await self._download_capture_if_supported(
                    orch,
                    destination_dir=str(session.session_dir),
                )
                capture_paths = [*perception_paths, *fallback_paths]
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
                        "sensor_rig_id": self.sensor_rig_id,
                        "reference_mapping_job_id": self.reference_mapping_job_id,
                        "perception_artifacts_count": len(perception_paths),
                        "direct_downloaded_paths_count": len(fallback_paths),
                        "direct_import_count": imported_direct,
                        "rosbag_paths": [
                            str(Path(path).name)
                            for path in perception_paths
                            if Path(path).suffix.lower() in {".db3", ".mcap", ".bag"}
                        ],
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

                client_flight_id = self._flight_token(orch)
                sync_result["client_flight_id"] = client_flight_id

                from backend.modules.warehouse.service.live_map_manifest import (
                    build_manifest_from_flight_dir,
                    finalize_manifest_integrity,
                    save_flight_manifest,
                    validate_save_quality,
                )

                pre_shutdown_diagnostics = await self._collect_mission_diagnostics(
                    orch,
                    phase="pre_finalize",
                )
                manifest_missing_topics = list(
                    pre_shutdown_diagnostics.get("missing_required_topics", [])
                ) + list(pre_shutdown_diagnostics.get("missing_nvblox_topics", []))
                manifest_localization_ok = bool(
                    pre_shutdown_diagnostics.get("can_localize")
                )

                def _build_save_validate_manifest():
                    # build_manifest_from_flight_dir scans + hashes every chunk file
                    # on disk (O(total bytes)); running it inline blocks the event
                    # loop for seconds during teardown. Offload the whole sync block
                    # to a worker thread so live WS clients / other flights keep moving.
                    built = build_manifest_from_flight_dir(
                        client_flight_id,
                        missing_topics=manifest_missing_topics,
                        localization_ok=manifest_localization_ok,
                        diagnostics_phase="pre_finalize",
                    )
                    built = finalize_manifest_integrity(built)
                    save_flight_manifest(built)
                    ok, detail = validate_save_quality(built)
                    return built, ok, detail

                manifest, save_ok, save_detail = await asyncio.to_thread(
                    _build_save_validate_manifest
                )
                sync_result["live_map_manifest"] = manifest.as_dict()
                sync_result["live_map_quality"] = {
                    "ok": save_ok,
                    "detail": save_detail,
                    "map_quality": manifest.map_quality,
                    "manifest_status": manifest.manifest_status,
                    "chunk_counts": dict(manifest.chunk_counts),
                    "point_counts": dict(manifest.point_counts),
                    "missing_topics": list(manifest.missing_topics),
                    "nvblox_available": manifest.nvblox_available,
                }
                live_map_chunk_total = sum(int(v) for v in manifest.chunk_counts.values())
                sync_result["live_map_chunk_total"] = live_map_chunk_total
                sync_result["live_map_manifest_status"] = manifest.manifest_status
                logger.info(
                    "Warehouse scan map readiness: capture_session_files=%s "
                    "live_map_chunks=%s manifest_status=%s nvblox_available=%s",
                    sync_result.get("file_count"),
                    live_map_chunk_total,
                    manifest.manifest_status,
                    manifest.nvblox_available,
                )
                if not save_ok:
                    raise RuntimeError(save_detail)
                sync_result["status"] = "ready"
                if not manifest.nvblox_available:
                    sync_result["status"] = "degraded"
                    sync_result["degradation_reason"] = "nvblox_unavailable"

                db_flight_id = getattr(orch, "_flight_id", None)
                if db_flight_id is not None:
                    sync_result["flight_id"] = db_flight_id

                mapping_result = await mapping_service.persist_capture(
                    owner_id=int(self.owner_id),
                    org_id=None,
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
                if client_flight_id:
                    from backend.modules.warehouse.service.live_map_stream import (
                        warehouse_live_map_stream,
                    )

                    job_id = mapping_result.get("job_id")
                    await warehouse_live_map_stream.finalize(
                        str(client_flight_id),
                        int(job_id) if job_id is not None else None,
                    )
                try:
                    from backend.modules.agents.hooks import schedule_warehouse_scan_postflight

                    schedule_warehouse_scan_postflight(
                        warehouse_map_id=int(self.warehouse_map_id),
                        client_flight_id=client_flight_id,
                        capture_result=dict(sync_result),
                    )
                except Exception:
                    logger.exception("Failed to schedule warehouse scan agent postflight")

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
        ros_mapping_status = "completed" if mapping_saved else (
            "failed" if mapping_error is not None else "skipped"
        )
        artifact_export_status = "exported" if mapping_saved else (
            "missing_outputs" if mapping_error is not None else "not_attempted"
        )
        overall_status = "completed"
        if mission_error is not None:
            overall_status = "failed"
        elif mapping_error is not None:
            overall_status = "partial_failure"

        if mission_error is not None:
            final_note = "Warehouse scan flight failed; 3D map persistence was skipped"
        elif mapping_saved:
            final_note = "Warehouse scan flight completed and 3D map persisted"
        elif mapping_error is not None:
            final_note = (
                "Flight completed, but warehouse mapping failed because no ROS mapping "
                f"artifacts were produced: {str(mapping_error)[:160]}"
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
                "video_capture_status": "completed" if video_recording_active else "not_started",
                "ros_mapping_status": ros_mapping_status,
                "artifact_export_status": artifact_export_status,
                "overall_status": overall_status,
                "scan_pattern": self.scan_pattern,
                "view_mode": self.view_mode,
                "layers": int(self.layer_count),
                "odometry_drift_m": self._latest_odometry_drift(orch),
            },
        )

        from backend.modules.warehouse.service.mapping_stack_lifecycle import (
            shutdown_warehouse_mapping_stack,
        )

        await self._log_mission_diagnostic_summary(
            orch,
            mission_error=mission_error,
            mapping_saved=mapping_saved,
            phase="pre_cleanup",
        )

        await self._mark_mission_runtime_terminal_safe(
            orch,
            mission_error=mission_error,
            mapping_error=mapping_error,
            mapping_saved=mapping_saved,
        )

        try:
            await shutdown_warehouse_mapping_stack()
        except Exception as exc:
            await self._add_event_safe(
                orch,
                "warehouse_scan_cleanup_failed",
                {"error": str(exc)},
            )
            logger.warning("Warehouse mapping cleanup failed", exc_info=True)

        await self._log_mission_diagnostic_summary(
            orch,
            mission_error=mission_error,
            mapping_saved=mapping_saved,
            phase="post_cleanup",
        )

        if mission_error is not None:
            raise mission_error
        if mapping_error is not None:
            raise WarehouseMissionFailure(
                reason="mapping_artifacts_missing",
                action="complete",
                stage="capture",
                message=(
                    "Flight completed, but warehouse mapping failed because no ROS mapping "
                    "artifacts were produced. Check RGB/depth/odometry/nvblox topics "
                    "before rerunning."
                ),
                details={
                    "mapping_error": str(mapping_error)[:500],
                    "overall_status": "partial_failure",
                    "artifact_export_status": "missing_outputs",
                },
            )
    # ------------------------------------------------------------------
    # Plan building
    # ------------------------------------------------------------------

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
            await asyncio.to_thread(orch.drone.follow_enu_setpoints, local_segment)
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

    # ------------------------------------------------------------------
    # Capture hooks
    # ------------------------------------------------------------------

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

    async def _collect_mission_diagnostics(
        self,
        orch: Orchestrator,
        *,
        phase: str,
    ) -> dict[str, object]:
        from backend.modules.warehouse.service.readiness_result import (
            readiness_from_perception_status_strict,
        )
        from backend.modules.warehouse.service.warehouse_preflight import (
            fetch_warehouse_perception_status,
        )

        del orch
        # After cleanup the mapping stack + ROS bridge are already torn down, so a
        # deep/forced probe just burns seconds on _ensure_ros_bridge_running +
        # `ros2 topic list` timeouts (and would try to restart the bridge). Use a
        # shallow, non-forcing probe for the post-cleanup snapshot.
        is_post_cleanup = phase == "post_cleanup"
        try:
            status = await fetch_warehouse_perception_status(
                deep=not is_post_cleanup,
                force=not is_post_cleanup,
            )
            readiness = readiness_from_perception_status_strict(status)
        except Exception as exc:
            logger.warning("Mission diagnostic health probe failed (%s): %s", phase, exc)
            return {"phase": phase, "probe_failed": True}

        return {
            "phase": phase,
            "bridge_alive": readiness.bridge_alive,
            "ros_graph_ready": readiness.ros_graph_ready,
            "can_localize": readiness.can_localize,
            "missing_required_topics": list(readiness.missing_required_topics),
            "missing_nvblox_topics": list(readiness.missing_nvblox_topics),
            "unhealthy_topics": list(readiness.unhealthy_topics),
        }

    def _latest_odometry_drift(self, orch: Orchestrator) -> float | None:
        snapshot = getattr(orch, "_last_telemetry_snapshot", None)
        if not isinstance(snapshot, dict):
            return None
        raw = snapshot.get("odometry_drift_m")
        try:
            return round(float(raw), 3) if raw is not None else None
        except (TypeError, ValueError):
            return None

    async def _log_mission_diagnostic_summary(
        self,
        orch: Orchestrator,
        *,
        mission_error: Exception | None,
        mapping_saved: bool,
        phase: str = "pre_cleanup",
    ) -> None:
        from backend.modules.warehouse.exceptions import WarehouseMissionFailure

        failure_code = None
        if isinstance(mission_error, WarehouseMissionFailure):
            failure_code = mission_error.reason

        diagnostics = await self._collect_mission_diagnostics(orch, phase=phase)

        summary: dict[str, object] = {
            "flight_id": getattr(orch, "_flight_id", None),
            "mission_type": self.mission_kind,
            "diagnostics_phase": phase,
            "result": (
                "failed"
                if mission_error
                else ("partial_failure" if not mapping_saved else "completed")
            ),
            "failure_code": failure_code,
            "mapping_saved": mapping_saved,
            "cleanup_completed": phase == "post_cleanup",
        }
        client_flight_id = self._flight_token(orch)
        from backend.modules.warehouse.service.live_map_manifest import (
            load_flight_manifest,
        )

        manifest = load_flight_manifest(client_flight_id)
        if manifest is not None:
            summary["live_map_manifest"] = manifest.as_dict()
            summary["quality_evidence"] = manifest.quality_evidence
            summary["localization_quality"] = manifest.localization_quality
            summary["map_quality"] = manifest.map_quality
        if diagnostics.get("probe_failed"):
            summary["probe_failed"] = True
        else:
            summary.update(
                {
                    "bridge_alive": diagnostics.get("bridge_alive"),
                    "ros_graph_ready": diagnostics.get("ros_graph_ready"),
                    "can_localize": diagnostics.get("can_localize"),
                    "missing_required_topics": diagnostics.get("missing_required_topics"),
                    "missing_nvblox_topics": diagnostics.get("missing_nvblox_topics"),
                    "unhealthy_topics": diagnostics.get("unhealthy_topics"),
                }
            )
            if manifest is None and phase == "post_cleanup":
                summary["quality_evidence"] = False
            elif manifest is not None and manifest.quality_evidence:
                summary["quality_evidence"] = True
                if not diagnostics.get("can_localize"):
                    summary["localization_quality"] = "degraded"

        logger.info("Warehouse mission diagnostic summary %s", summary)
        await self._add_event_safe(orch, "warehouse_mission_diagnostic", summary)

    async def _check_runtime_safety(self, orch: Orchestrator) -> None:
        deep = self._runtime_safety.should_run_deep_health_probe()
        try:
            status = await build_warehouse_perception_port().status(
                deep=deep,
                force=False,
            )
        except Exception as exc:
            logger.warning("Warehouse runtime safety health check failed: %s", exc)
            return
        if deep:
            self._runtime_safety.mark_deep_probe_ran()

        components = status.components if isinstance(status.components, dict) else {}
        components = dict(components)
        from backend.modules.warehouse.service.runtime_safety import read_odometry_state_file

        odom_read = read_odometry_state_file()
        if odom_read.unreadable:
            components["odometry_state_unreadable"] = True
            components["local_odometry_state"] = {}
        elif odom_read.payload:
            components["local_odometry_state"] = odom_read.payload
        from backend.modules.warehouse.service.runtime_safety import (
            merge_runtime_odometry_components,
        )

        components = merge_runtime_odometry_components(components)
        decision = self._runtime_safety.evaluate(
            components,
            deep_health=deep,
            min_localization_confidence=float(self.localization_confidence_min),
            min_obstacle_distance_m=float(self.clearance_m),
            min_ceiling_distance_m=float(self.ceiling_margin_m),
        )
        from backend.modules.warehouse.service.flight_watchdog import (
            apply_watchdog_to_safety_decision,
            get_warehouse_flight_watchdog,
        )

        watchdog = get_warehouse_flight_watchdog()
        if not watchdog.active:
            watchdog.start()
        watchdog_action = watchdog.evaluate(components=components, status=status)
        if watchdog_action.triggered:
            decision = apply_watchdog_to_safety_decision(watchdog_action)
        if decision.safe:
            return
        await self._add_event_safe(
            orch,
            "warehouse_safety_abort",
            {
                "reason": decision.reason,
                "action": decision.action,
                "details": decision.details or {},
                "deep_health": deep,
            },
        )
        raise WarehouseMissionFailure(
            reason=decision.reason or "warehouse_safety_abort",
            action=decision.action,
            stage="flight",
            message=f"Warehouse safety abort: {decision.reason}",
            details=decision.details or {},
        )

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
        drone_start = getattr(orch.drone, "start_video_recording", None)
        if callable(drone_start):
            try:
                drone_started = bool(await asyncio.to_thread(drone_start))
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
        drone_stop = getattr(orch.drone, "stop_video_recording", None)
        if callable(drone_stop):
            try:
                drone_stopped = bool(await asyncio.to_thread(drone_stop))
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
