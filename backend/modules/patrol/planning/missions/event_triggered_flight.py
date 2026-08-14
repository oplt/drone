from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from backend.modules.patrol.geo import point_in_polygon
from backend.modules.patrol.planning.event_response import generate_event_triggered_patrol_plan
from backend.modules.patrol.planning.ml_binding import patrol_ml_runtime_payload
from backend.modules.patrol.vision.runtime import ml_runtime
from backend.modules.vehicle_runtime.orchestrator import Orchestrator
from backend.modules.vehicle_runtime.types import Coordinate

logger = logging.getLogger(__name__)


class EventTriggeredPatrolFlightMixin:
    async def _fly_incident_verification(
        self,
        orch: Orchestrator,
        *,
        event_point: Coordinate,
        verification_path: list[Coordinate],
        report: dict[str, Any],
    ) -> None:
        await orch.async_drone.follow_waypoints([event_point])
        orch._dest_coord = event_point
        await self._add_event_safe(
            orch,
            "private_patrol_event_location_reached",
            {"lat": float(event_point.lat), "lon": float(event_point.lon)},
        )

        tracking_started, tracking_method = await self._maybe_start_tracking(orch, event_point)
        if verification_path:
            await orch.async_drone.follow_waypoints(verification_path)
            await self._add_event_safe(
                orch,
                "private_patrol_event_verification_path_completed",
                {"waypoints": len(verification_path)},
            )

        report["ai_verified"] = await self._wait_for_ai_verification(orch)
        await self._loiter_if_configured(orch)

        if tracking_started:
            tracking_stopped = await self._stop_tracking(orch)
            await self._add_event_safe(
                orch,
                "private_patrol_tracking_stopped",
                {
                    "stopped": bool(tracking_stopped),
                    "method": tracking_method,
                },
            )

    async def _fly_detection_search(
        self,
        orch: Orchestrator,
        *,
        cruise_alt_m: float,
        baseline_anomalies: int,
        report: dict[str, Any],
    ) -> Coordinate | None:
        search_plan = self._make_search_plan(altitude_agl=cruise_alt_m)
        route = search_plan.waypoints
        if len(route) < 2:
            raise ValueError("Detection/search requires a grid route with at least 2 waypoints")

        await self._add_event_safe(
            orch,
            "private_patrol_detection_search_started",
            {"waypoints": len(route), "grid_spacing_m": float(self.search_grid_spacing_m)},
        )

        segment_size = 5
        focused: Coordinate | None = None
        for start_idx in range(0, len(route), segment_size):
            segment = route[start_idx : start_idx + segment_size]
            await orch.async_drone.follow_waypoints(segment)
            focused = await self._poll_incident_focus(
                orch,
                baseline_anomalies=baseline_anomalies,
            )
            if focused is not None:
                report["search_incident_detected"] = True
                await self._add_event_safe(
                    orch,
                    "private_patrol_search_incident_focus",
                    {"lat": float(focused.lat), "lon": float(focused.lon)},
                )
                incident_plan = generate_event_triggered_patrol_plan(
                    (float(focused.lon), float(focused.lat)),
                    altitude_agl_m=float(cruise_alt_m),
                    verification_radius_m=float(self.verification_radius_m),
                    geofence_polygon_lonlat=self.geofence_polygon_lonlat,
                )
                await self._fly_incident_verification(
                    orch,
                    event_point=incident_plan.waypoints[0],
                    verification_path=list(incident_plan.waypoints[1:]),
                    report=report,
                )
                return focused

        report["search_incident_detected"] = False
        return None

    async def _poll_incident_focus(
        self,
        orch: Orchestrator,
        *,
        baseline_anomalies: int,
    ) -> Coordinate | None:
        status = ml_runtime.status()
        anomalies = int(status.get("anomalies_emitted", 0) or 0)
        if anomalies <= baseline_anomalies:
            return None

        try:
            telemetry = await orch.async_drone.get_telemetry()
        except Exception:
            return None

        lat = getattr(telemetry, "lat", None)
        lon = getattr(telemetry, "lon", None)
        if lat is None or lon is None:
            return None

        if not point_in_polygon(float(lat), float(lon), self.geofence_polygon_lonlat):
            return None

        alt = getattr(telemetry, "alt", None) or getattr(telemetry, "relative_alt", None)
        return Coordinate(lat=float(lat), lon=float(lon), alt=float(alt or self.altitude_agl))

    async def _wait_for_ai_verification(self, orch: Orchestrator) -> bool:
        _ = orch
        deadline = time.monotonic() + min(float(self.verification_loiter_s), 30.0)
        while time.monotonic() < deadline:
            status = ml_runtime.status()
            if int(status.get("anomalies_emitted", 0) or 0) > 0:
                return True
            if status.get("last_error"):
                break
            await asyncio.sleep(1.0)
        return int(ml_runtime.status().get("anomalies_emitted", 0) or 0) > 0

    async def _loiter_if_configured(self, orch: Orchestrator) -> None:
        if float(self.verification_loiter_s) <= 0:
            return
        await asyncio.sleep(float(self.verification_loiter_s))
        await self._add_event_safe(
            orch,
            "private_patrol_event_verification_loiter_completed",
            {"duration_s": float(self.verification_loiter_s)},
        )

    async def _maybe_start_tracking(
        self,
        orch: Orchestrator,
        event_point: Coordinate,
    ) -> tuple[bool, str | None]:
        if not self.track_target:
            await self._add_event_safe(
                orch,
                "private_patrol_tracking_started",
                {"requested": False, "started": False, "method": None},
            )
            return False, None

        tracking_started, tracking_method = await self._start_tracking(orch, event_point)
        await self._add_event_safe(
            orch,
            "private_patrol_tracking_started",
            {
                "requested": True,
                "started": bool(tracking_started),
                "method": tracking_method,
                "target_label": str(self.target_label).strip() if self.target_label else None,
            },
        )
        return tracking_started, tracking_method

    async def _return_home(self, orch: Orchestrator, home: Coordinate) -> None:
        await orch.async_drone.follow_waypoints([home])
        await self._add_event_safe(orch, "reached_destination", {})
        await orch.async_drone.land()
        await self._add_event_safe(orch, "landing_command_sent", {})
        await orch.async_drone.wait_until_disarmed(900)
        await self._add_event_safe(orch, "landed_home", {})

    async def _save_trigger_report(self, orch: Orchestrator, report: dict[str, Any]) -> None:
        report["ml_runtime"] = patrol_ml_runtime_payload(orch)
        await self._add_event_safe(orch, "private_patrol_trigger_report", report)

    async def _start_video_stream(self, orch: Orchestrator) -> bool:
        if callable(getattr(orch.drone, "start_video_recording", None)):
            try:
                return await orch.async_drone.start_video_recording()
            except Exception:
                return False
        return False

    async def _stop_video_stream(self, orch: Orchestrator) -> bool:
        if callable(getattr(orch.drone, "stop_video_recording", None)):
            try:
                return await orch.async_drone.stop_video_recording()
            except Exception:
                return False
        return False

    async def _start_tracking(
        self,
        orch: Orchestrator,
        event_point: Coordinate,
    ) -> tuple[bool, str | None]:
        method_names = [
            "start_tracking",
            "start_target_tracking",
            "start_object_tracking",
            "track_target",
        ]
        for method_name in method_names:
            if not callable(getattr(orch.drone, method_name, None)):
                continue
            try:
                result = await orch.async_drone.optional_call(
                    method_name,
                    target_label=(str(self.target_label).strip() if self.target_label else None),
                    lat=float(event_point.lat),
                    lon=float(event_point.lon),
                )
                return bool(result if result is not None else True), method_name
            except TypeError:
                try:
                    result = await orch.async_drone.optional_call(method_name, event_point)
                    return bool(result if result is not None else True), method_name
                except TypeError:
                    try:
                        result = await orch.async_drone.optional_call(method_name)
                        return bool(result if result is not None else True), method_name
                    except Exception:
                        continue
                except Exception:
                    continue
            except Exception:
                continue
        return False, None

    async def _stop_tracking(self, orch: Orchestrator) -> bool:
        for method_name in (
            "stop_tracking",
            "stop_target_tracking",
            "stop_object_tracking",
        ):
            fn = getattr(orch.drone, method_name, None)
            if not callable(fn):
                continue
            try:
                result = await asyncio.to_thread(fn)
                return bool(result if result is not None else True)
            except Exception:
                continue
        return False
