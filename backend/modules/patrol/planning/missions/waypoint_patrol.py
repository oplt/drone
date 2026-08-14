from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from backend.core.types.geo import coord_from_home
from backend.modules.missions.flight_models import FlightStatus
from backend.modules.patrol.ai_tasks import PATROL_AI_TASKS
from backend.modules.patrol.planning.geometry import (
    dynamic_trigger_profile,
)
from backend.modules.patrol.planning.ml_binding import (
    patrol_ml_runtime_payload,
    start_patrol_ml_runtime,
    stop_patrol_ml_runtime,
)
from backend.modules.patrol.planning.models import PrivatePatrolPlan
from backend.modules.patrol.planning.normalization import (
    normalize_ai_tasks,
)
from backend.modules.patrol.planning.types import (
    PatrolTask,
)
from backend.modules.patrol.planning.waypoint import generate_waypoint_patrol_plan
from backend.modules.vehicle_runtime.orchestrator import Orchestrator
from backend.modules.vehicle_runtime.types import Coordinate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WaypointPatrolMission:
    key_points_lonlat: list[tuple[float, float]]
    altitude_agl: float = 30.0
    speed_mps: float = 5.0
    hover_time_s: float = 15.0
    camera_scan_yaw_deg: float = 360.0
    zoom_capture: bool = True
    return_to_start: bool = True
    record_video_stream: bool = True
    ai_tasks: tuple[PatrolTask, ...] = PATROL_AI_TASKS

    mission_type: str = "private_patrol_waypoint"

    def __post_init__(self) -> None:
        if len(self.key_points_lonlat) < 2:
            raise ValueError("Waypoint patrol requires at least 2 key points")
        if float(self.altitude_agl) <= 0:
            raise ValueError("altitude_agl must be > 0")
        if float(self.speed_mps) <= 0:
            raise ValueError("speed_mps must be > 0")
        if float(self.hover_time_s) <= 0:
            raise ValueError("hover_time_s must be > 0")
        if not 0.0 <= float(self.camera_scan_yaw_deg) <= 360.0:
            raise ValueError("camera_scan_yaw_deg must be between 0 and 360")
        object.__setattr__(self, "ai_tasks", normalize_ai_tasks(self.ai_tasks))

    def _make_plan(self, *, altitude_agl: float | None = None) -> PrivatePatrolPlan:
        return generate_waypoint_patrol_plan(
            self.key_points_lonlat,
            altitude_agl_m=float(self.altitude_agl if altitude_agl is None else altitude_agl),
            return_to_start=bool(self.return_to_start),
        )

    def get_waypoints(self) -> list[Coordinate]:
        return self._make_plan().waypoints

    async def execute(self, orch: Orchestrator, alt: float) -> None:
        effective_alt = float(alt if alt is not None else self.altitude_agl)
        ml_binding = await start_patrol_ml_runtime(orch, ai_tasks=list(self.ai_tasks))
        try:
            await orch.run_mission(
                self,
                alt=effective_alt,
                flight_fn=lambda: self.fly_waypoint_patrol(orch, cruise_alt_m=effective_alt),
            )
        finally:
            await stop_patrol_ml_runtime(ml_binding)

    async def fly_waypoint_patrol(self, orch: Orchestrator, *, cruise_alt_m: float) -> None:
        plan = self._make_plan(altitude_agl=cruise_alt_m)
        keypoints = plan.waypoints
        if len(keypoints) < 2:
            raise ValueError("Waypoint patrol route requires at least 2 points")

        home = coord_from_home(orch.drone.home_location)
        home.alt = float(cruise_alt_m)

        await self._add_event_safe(
            orch,
            "private_patrol_waypoint_plan_generated",
            {
                **plan.stats,
                "speed_mps": float(self.speed_mps),
                "hover_time_s": float(self.hover_time_s),
                "camera_scan_yaw_deg": float(self.camera_scan_yaw_deg),
                "zoom_capture": bool(self.zoom_capture),
                "ai_tasks": list(self.ai_tasks),
            },
        )

        await self._add_event_safe(
            orch,
            "private_patrol_ai_configured",
            {
                "tasks": list(self.ai_tasks),
                "dynamic_triggers": dynamic_trigger_profile(
                    ai_tasks=self.ai_tasks,
                    path_offset_m=0.0,
                ),
            },
        )
        await self._add_event_safe(
            orch,
            "private_patrol_ml_runtime",
            patrol_ml_runtime_payload(orch),
        )

        try:
            speed_set = await orch.async_drone.set_groundspeed(float(self.speed_mps))
            await self._add_event_safe(
                orch,
                "private_patrol_speed_configured",
                {"speed_mps": float(self.speed_mps), "applied": bool(speed_set)},
            )
        except Exception as exc:
            await self._add_event_safe(
                orch,
                "private_patrol_speed_config_failed",
                {"speed_mps": float(self.speed_mps), "error": str(exc)},
            )

        await asyncio.sleep(1.0)
        await orch.async_drone.arm_and_takeoff(float(cruise_alt_m))
        await self._add_event_safe(orch, "takeoff", {})

        for idx, checkpoint in enumerate(keypoints, start=1):
            await orch.async_drone.follow_waypoints([checkpoint])
            orch._dest_coord = checkpoint
            await self._add_event_safe(
                orch,
                "private_patrol_checkpoint_arrived",
                {
                    "index": idx,
                    "lat": float(checkpoint.lat),
                    "lon": float(checkpoint.lon),
                },
            )
            await self._run_checkpoint_actions(
                orch,
                checkpoint_index=idx,
                checkpoint=checkpoint,
            )

        await orch.async_drone.follow_waypoints([home])
        await self._add_event_safe(orch, "reached_destination", {})

        await orch.async_drone.land()
        await self._add_event_safe(orch, "landing_command_sent", {})

        await orch.async_drone.wait_until_disarmed(900)
        await self._add_event_safe(orch, "landed_home", {})

        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is not None:
            await orch.repo.finish_flight(
                flight_id,
                status=FlightStatus.COMPLETED,
                note="Private waypoint patrol completed and returned home",
            )

    async def _run_checkpoint_actions(
        self,
        orch: Orchestrator,
        *,
        checkpoint_index: int,
        checkpoint: Coordinate,
    ) -> None:
        started = asyncio.get_running_loop().time()
        scan_result = await self._camera_scan(orch)
        zoom_result = await self._zoom_capture(orch)
        elapsed = asyncio.get_running_loop().time() - started
        remaining_hover_s = max(0.0, float(self.hover_time_s) - elapsed)
        if remaining_hover_s > 0.0:
            await asyncio.sleep(remaining_hover_s)

        await self._add_event_safe(
            orch,
            "private_patrol_checkpoint_actions_completed",
            {
                "index": int(checkpoint_index),
                "lat": float(checkpoint.lat),
                "lon": float(checkpoint.lon),
                "hover_time_s": float(self.hover_time_s),
                "camera_scan_yaw_deg": float(self.camera_scan_yaw_deg),
                "camera_scan_applied": bool(scan_result.get("applied")),
                "camera_scan_method": scan_result.get("method"),
                "zoom_capture": bool(self.zoom_capture),
                "zoom_capture_applied": bool(zoom_result.get("applied")),
                "zoom_capture_method": zoom_result.get("method"),
            },
        )

    async def _camera_scan(self, orch: Orchestrator) -> dict[str, Any]:
        if float(self.camera_scan_yaw_deg) <= 0:
            return {"applied": False, "method": None}

        method_specs: list[tuple[str, dict[str, Any]]] = [
            ("scan_yaw_360", {}),
            ("camera_scan_360", {}),
            ("condition_yaw", {"heading_deg": float(self.camera_scan_yaw_deg)}),
            ("set_yaw", {"yaw_deg": float(self.camera_scan_yaw_deg)}),
        ]
        for method_name, kwargs in method_specs:
            if not callable(getattr(orch.drone, method_name, None)):
                continue
            try:
                await orch.async_drone.optional_call(method_name, **kwargs)
                return {"applied": True, "method": method_name}
            except TypeError:
                try:
                    await orch.async_drone.optional_call(
                        method_name, float(self.camera_scan_yaw_deg)
                    )
                    return {"applied": True, "method": method_name}
                except Exception:
                    continue
            except Exception:
                continue

        return {"applied": False, "method": None}

    async def _zoom_capture(self, orch: Orchestrator) -> dict[str, Any]:
        if not self.zoom_capture:
            return {"applied": False, "method": None}

        method_specs: list[tuple[str, dict[str, Any]]] = [
            ("capture_zoom_photo", {"zoom_level": 2.0}),
            ("capture_photo", {}),
            ("trigger_camera_capture", {}),
        ]
        for method_name, kwargs in method_specs:
            if not callable(getattr(orch.drone, method_name, None)):
                continue
            try:
                await orch.async_drone.optional_call(method_name, **kwargs)
                return {"applied": True, "method": method_name}
            except TypeError:
                try:
                    await orch.async_drone.optional_call(method_name)
                    return {"applied": True, "method": method_name}
                except Exception:
                    continue
            except Exception:
                continue

        if callable(getattr(orch.drone, "start_image_capture", None)) and callable(
            getattr(orch.drone, "stop_image_capture", None)
        ):
            try:
                started = bool(
                    await orch.async_drone.start_image_capture(
                        mode="time",
                        interval_s=0.7,
                    )
                )
                await asyncio.sleep(1.2)
                await orch.async_drone.stop_image_capture()
                return {"applied": started, "method": "start_image_capture(time)"}
            except Exception:
                return {"applied": False, "method": None}

        return {"applied": False, "method": None}

    async def _add_event_safe(
        self,
        orch: Orchestrator,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is None:
            return
        try:
            await orch.repo.add_event(flight_id, event_type, data or {})
        except Exception:
            logger.exception(
                "WaypointPatrolMission: failed to persist event '%s' for flight_id=%s",
                event_type,
                flight_id,
            )


