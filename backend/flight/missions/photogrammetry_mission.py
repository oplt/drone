from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, List, Literal, Tuple

from backend.db.models import FlightStatus
from backend.drone.models import Coordinate
from backend.drone.orchestrator import Orchestrator
from backend.flight.missions.terrain_follow import (
    apply_terrain_follow_to_path,
    resolve_home_amsl_m,
)
from backend.services.photogrammetry.flight_capture import FlightCaptureSessionService
from backend.services.photogrammetry.mission import make_photogrammetry_plan
from backend.utils.geo import coord_from_home


logger = logging.getLogger(__name__)



@dataclass(frozen=True)
class PhotogrammetryMission:
    polygon_lonlat: List[Tuple[float, float]]  # [(lon,lat),...]
    altitude_agl: float
    fov_h: float
    fov_v: float
    front_overlap: float
    side_overlap: float
    min_spacing_m: float = 0.5
    heading_deg: float = 0.0
    speed_mps: float = 3.0
    trigger_mode: Literal["distance", "time"] = "distance"
    trigger_distance_m: float = 2.5
    trigger_interval_s: float = 1.0
    await_image_sync: bool = True
    image_sync_wait_timeout_s: float = 120.0
    image_sync_poll_interval_s: float = 2.0
    image_sync_min_count: int = 1
    terrain_follow: bool = False
    terrain_target_agl_m: float | None = None
    terrain_min_rel_alt_m: float = 10.0
    terrain_max_rel_alt_m: float = 120.0
    terrain_max_step_m: float = 3.0

    mission_type: str = "photogrammetry"

    def get_waypoints(self) -> list[Coordinate]:
        plan = make_photogrammetry_plan(
            polygon_lonlat=self.polygon_lonlat,
            altitude_agl=self.altitude_agl,
            fov_h=self.fov_h,
            fov_v=self.fov_v,
            front_overlap=self.front_overlap,
            side_overlap=self.side_overlap,
            heading_deg=self.heading_deg,
            min_spacing_m=self.min_spacing_m,
        )
        return plan.waypoints

    async def _add_event_safe(
        self,
        orch: Orchestrator,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is None:
            logger.warning(
                "PhotogrammetryMission: flight_id unavailable; skipping event '%s'",
                event_type,
            )
            return
        try:
            await orch.repo.add_event(flight_id, event_type, data or {})
        except Exception as exc:
            logger.warning(
                "PhotogrammetryMission: failed to write event '%s': %s",
                event_type,
                exc,
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
            logger.warning(
                "PhotogrammetryMission: flight_id unavailable; cannot finish flight with status=%s",
                status.value,
            )
            return False

        safe_note = (note or "").strip()
        if len(safe_note) > 250:
            safe_note = safe_note[:247] + "..."

        try:
            await orch.repo.finish_flight(
                flight_id,
                status=status,
                note=safe_note,
            )
            return True
        except Exception as exc:
            logger.warning(
                "PhotogrammetryMission: failed to finish flight_id=%s status=%s: %s",
                flight_id,
                status.value,
                exc,
            )
            return False

    async def _configure_capture(self, orch: Orchestrator) -> tuple[bool, str]:
        try:
            speed_ok = await asyncio.to_thread(orch.drone.set_groundspeed, self.speed_mps)
            await self._add_event_safe(
                orch,
                "photogrammetry_speed_configured",
                {"speed_mps": self.speed_mps, "applied": bool(speed_ok)},
            )
        except Exception as exc:
            await self._add_event_safe(
                orch,
                "photogrammetry_speed_config_failed",
                {"speed_mps": self.speed_mps, "error": str(exc)},
            )
            logger.warning("Failed to apply groundspeed %.2f m/s: %s", self.speed_mps, exc)

        capture_kwargs: dict[str, Any] = {"mode": self.trigger_mode}
        if self.trigger_mode == "distance":
            capture_kwargs["distance_m"] = self.trigger_distance_m
            capture_meta = {"mode": "distance", "distance_m": self.trigger_distance_m}
        else:
            capture_kwargs["interval_s"] = self.trigger_interval_s
            capture_meta = {"mode": "time", "interval_s": self.trigger_interval_s}

        try:
            started = await asyncio.to_thread(orch.drone.start_image_capture, **capture_kwargs)
            if started:
                await self._add_event_safe(
                    orch,
                    "photogrammetry_capture_started",
                    capture_meta,
                )
                return True, ""
            msg = "Drone image capture is unsupported on current vehicle adapter."
            await self._add_event_safe(
                orch,
                "photogrammetry_capture_unavailable",
                {**capture_meta, "reason": msg},
            )
            return False, msg
        except Exception as exc:
            await self._add_event_safe(
                orch,
                "photogrammetry_capture_failed",
                {**capture_meta, "error": str(exc)},
            )
            return False, str(exc)

    async def _stop_capture(self, orch: Orchestrator) -> None:
        try:
            stopped = await asyncio.to_thread(orch.drone.stop_image_capture)
            await self._add_event_safe(
                orch,
                "photogrammetry_capture_stopped",
                {"stopped": bool(stopped)},
            )
        except Exception as exc:
            await self._add_event_safe(
                orch,
                "photogrammetry_capture_stop_failed",
                {"error": str(exc)},
            )
            logger.warning("Failed to stop image capture cleanly: %s", exc)

    async def fly_photogrammetry(self, orch: Orchestrator, cruise_alt: float) -> None:
        waypoints = self.get_waypoints()
        if len(waypoints) < 2:
            raise ValueError("Need at least 2 waypoints to execute photogrammetry mission.")

        planned_agl_m = float(self.altitude_agl)
        target_agl_m = float(
            self.terrain_target_agl_m
            if self.terrain_target_agl_m is not None
            else planned_agl_m
        )
        takeoff_alt_m = target_agl_m if self.terrain_follow else planned_agl_m

        if self.terrain_follow:
            home_amsl_m = await asyncio.to_thread(resolve_home_amsl_m, orch.drone)
            waypoints = await apply_terrain_follow_to_path(
                maps_client=orch.maps,
                path=waypoints,
                home_amsl_m=home_amsl_m,
                target_agl_m=target_agl_m,
                min_rel_alt_m=float(self.terrain_min_rel_alt_m),
                max_rel_alt_m=float(self.terrain_max_rel_alt_m),
                max_step_m=float(self.terrain_max_step_m),
            )
            await self._add_event_safe(
                orch,
                "photogrammetry_terrain_follow_applied",
                {
                    "waypoints": len(waypoints),
                    "target_agl_m": target_agl_m,
                    "takeoff_alt_m": takeoff_alt_m,
                },
            )

        logger.info(
            "Photogrammetry mission start: flight_id=%s waypoints=%s takeoff_alt=%s "
            "planned_agl=%s requested_cruise_alt=%s trigger_mode=%s terrain_follow=%s",
            getattr(orch, "_flight_id", None),
            len(waypoints),
            takeoff_alt_m,
            planned_agl_m,
            cruise_alt,
            self.trigger_mode,
            self.terrain_follow,
        )
        home = coord_from_home(orch.drone.home_location)
        home.alt = float(waypoints[-1].alt if waypoints and waypoints[-1].alt is not None else takeoff_alt_m)

        capture_session_service = FlightCaptureSessionService()
        session = capture_session_service.start_session(flight_id=getattr(orch, "_flight_id", "unknown"))
        logger.info(
            "Photogrammetry capture session started: flight_id=%s source_dir=%s abs_dir=%s",
            session.flight_id,
            session.relative_source_dir,
            session.session_dir,
        )
        await self._add_event_safe(
            orch,
            "photogrammetry_capture_session_started",
            {
                "source_dir": session.relative_source_dir,
                "absolute_dir": str(session.session_dir),
            },
        )

        mission_error: Exception | None = None
        capture_started = False
        flight_finalized = False

        await asyncio.sleep(1.0)
        logger.info("Photogrammetry takeoff command: target_alt=%s", takeoff_alt_m)
        await asyncio.to_thread(orch.drone.arm_and_takeoff, takeoff_alt_m)
        await self._add_event_safe(orch, "takeoff", {})

        capture_started, capture_error = await self._configure_capture(orch)
        if not capture_started and capture_error:
            logger.warning("Photogrammetry capture did not start: %s", capture_error)
        else:
            logger.info("Photogrammetry capture active for flight_id=%s", session.flight_id)

        try:
            logger.info("Photogrammetry waypoint traversal started: count=%s", len(waypoints))
            await asyncio.to_thread(orch.drone.follow_waypoints, waypoints)
            await self._add_event_safe(orch, "reached_destination", {})
            logger.info("Photogrammetry waypoint traversal completed")
        except Exception as exc:
            mission_error = exc
            logger.error("Photogrammetry waypoint traversal failed: %s", exc)
            await self._add_event_safe(
                orch,
                "photogrammetry_path_failed",
                {"error": str(exc)},
            )
        finally:
            if capture_started:
                await self._stop_capture(orch)

        try:
            await asyncio.to_thread(orch.drone.follow_waypoints, [home])
            await self._add_event_safe(
                orch,
                "photogrammetry_return_home_completed",
                {"lat": float(home.lat), "lon": float(home.lon)},
            )
        except Exception as exc:
            if mission_error is None:
                mission_error = exc
            logger.error("Photogrammetry return-home leg failed: %s", exc)
            await self._add_event_safe(
                orch,
                "photogrammetry_return_home_failed",
                {"error": str(exc)},
            )

        try:
            logger.info("Photogrammetry landing command issued")
            await asyncio.to_thread(orch.drone.land)
            await self._add_event_safe(orch, "landing_command_sent", {})

            await asyncio.to_thread(orch.drone.wait_until_disarmed, 900)
            await self._add_event_safe(orch, "landed_home", {})
            status_at_touchdown = (
                FlightStatus.COMPLETED if mission_error is None else FlightStatus.FAILED
            )
            note_at_touchdown = (
                "Photogrammetry flight returned home, landed, and disarmed"
                if status_at_touchdown == FlightStatus.COMPLETED
                else "Photogrammetry flight landed/disarmed after mission error"
            )
            flight_finalized = await self._finish_flight_safe(
                orch,
                status=status_at_touchdown,
                note=note_at_touchdown,
            )
            logger.info("Photogrammetry landing complete and drone disarmed")
        except Exception as exc:
            logger.error("Photogrammetry landing failed: %s", exc)
            await self._add_event_safe(
                orch,
                "photogrammetry_landing_failed",
                {"error": str(exc)},
            )
            if mission_error is None:
                mission_error = exc
            flight_finalized = await self._finish_flight_safe(
                orch,
                status=FlightStatus.FAILED,
                note=f"Landing/disarm failed: {exc}",
            )

        min_images = self.image_sync_min_count if self.await_image_sync else 0
        wait_timeout = self.image_sync_wait_timeout_s if self.await_image_sync else 0.0
        direct_download_paths = await asyncio.to_thread(
            orch.drone.download_captured_images,
            destination_dir=str(session.session_dir),
        )
        imported_direct = await asyncio.to_thread(
            capture_session_service.import_external_images,
            session,
            image_paths=direct_download_paths,
        )
        sync_trigger = await asyncio.to_thread(
            capture_session_service.trigger_external_sync,
            session,
        )
        logger.info(
            "Photogrammetry image transfer stage: direct_downloaded=%s imported=%s sync_ok=%s",
            len(direct_download_paths or []),
            imported_direct,
            sync_trigger.get("ok"),
        )
        await self._add_event_safe(
            orch,
            "photogrammetry_direct_download",
            {
                "downloaded_paths_count": len(direct_download_paths or []),
                "imported_count": imported_direct,
            },
        )
        await self._add_event_safe(
            orch,
            "photogrammetry_external_sync",
            sync_trigger,
        )
        sync_result = await asyncio.to_thread(
            capture_session_service.finalize_session,
            session,
            min_images=min_images,
            timeout_s=wait_timeout,
            poll_interval_s=self.image_sync_poll_interval_s,
            extra_meta={
                "trigger_mode": self.trigger_mode,
                "trigger_distance_m": self.trigger_distance_m,
                "trigger_interval_s": self.trigger_interval_s,
                "speed_mps": self.speed_mps,
                "waypoints": len(waypoints),
            },
        )
        logger.info(
            "Photogrammetry session finalized: status=%s image_count=%s source_dir=%s",
            sync_result.get("status"),
            sync_result.get("image_count", 0),
            sync_result.get("source_dir"),
        )
        await self._add_event_safe(
            orch,
            "photogrammetry_images_staged",
            {
                "source_dir": sync_result.get("source_dir"),
                "image_count": sync_result.get("image_count", 0),
                "status": sync_result.get("status"),
            },
        )
        mapping_job_params = {
            "input_source": "drone_sync",
            "drone_sync": {
                "source_dir": sync_result.get("source_dir"),
            },
        }
        await self._add_event_safe(
            orch,
            "photogrammetry_mapping_job_params",
            mapping_job_params,
        )

        if not flight_finalized:
            status = (
                FlightStatus.COMPLETED
                if mission_error is None
                else FlightStatus.FAILED
            )
            await self._finish_flight_safe(
                orch,
                status=status,
                note=f"Photogrammetry mission {status.value}",
            )
        if mission_error is not None:
            logger.error("Photogrammetry mission finished with error: %s", mission_error)
            raise mission_error
        logger.info("Photogrammetry mission finished successfully: flight_id=%s", orch._flight_id)

    async def execute(self, orch: Orchestrator, alt: float) -> None:
        effective_alt = (
            float(self.terrain_target_agl_m)
            if self.terrain_follow and self.terrain_target_agl_m is not None
            else float(self.altitude_agl)
        )

        async def _flight_fn() -> None:
            await self.fly_photogrammetry(orch, cruise_alt=effective_alt)

        await orch.run_mission(
            self,
            alt=effective_alt,
            flight_fn=_flight_fn,
        )
