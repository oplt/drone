from __future__ import annotations

import logging

from dronekit import LocationGlobalRelative, VehicleMode

from backend.infrastructure.vehicle.mavlink._client_refs import client_module
from backend.infrastructure.vehicle.mavlink.config import logger
from backend.modules.vehicle_runtime.types import Coordinate
from backend.observability.instruments import structured_error
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record


class MavlinkNavigationMixin:
    """Goto, mode changes, and mission pause/resume/abort."""

    def goto(self, coord: Coordinate) -> None:
        # Send heartbeat before major operations
        # self.send_heartbeat()
        started = client_module().time.monotonic()
        with client_module().observed_span(
            "mavlink.goto_waypoint",
            drone_id="mavlink",
            mavlink_command="goto_waypoint",
            **{
                "mavlink.command.params": (
                    f"lat={coord.lat:.7f},lon={coord.lon:.7f},alt={coord.alt:.2f}"
                ),
                "mavlink.ack.result": "unknown",
                "mavlink.retry_count": 0,
            },
        ):
            try:
                target = LocationGlobalRelative(coord.lat, coord.lon, coord.alt)
                groundspeed = self._groundspeed_override_mps
                if groundspeed and groundspeed > 0:
                    self.vehicle.simple_goto(target, groundspeed=float(groundspeed))
                else:
                    self.vehicle.simple_goto(target)
                metric_record(
                    "mavlink_latency",
                    (client_module().time.monotonic() - started) * 1000.0,
                    {"command": "goto_waypoint", "result": "success"},
                )
            except Exception as exc:
                metric_add("mavlink_failures", attrs={"command": "goto_waypoint"})
                structured_error(
                    logger,
                    "mavlink_command_failed",
                    exc,
                    mavlink_command="goto_waypoint",
                    latency_ms=(client_module().time.monotonic() - started) * 1000.0,
                )
                raise

    def set_mode(self, mode: str) -> None:
        if not self.vehicle:
            raise RuntimeError("Vehicle not connected")
        started = client_module().time.monotonic()
        with client_module().observed_span("mavlink.set_mode", drone_id="mavlink", mavlink_command="set_mode"):
            try:
                self.vehicle.mode = VehicleMode(mode)
                metric_record(
                    "mavlink_latency",
                    (client_module().time.monotonic() - started) * 1000.0,
                    {"command": "set_mode", "result": "success"},
                )
            except Exception as exc:
                metric_add("mavlink_failures", attrs={"command": "set_mode"})
                structured_error(
                    logger,
                    "mavlink_command_failed",
                    exc,
                    mavlink_command="set_mode",
                    latency_ms=(client_module().time.monotonic() - started) * 1000.0,
                )
                raise

    def _set_mode_best_effort(self, *modes: str) -> bool:
        if not self.vehicle:
            return False
        for mode in modes:
            try:
                self.vehicle.mode = VehicleMode(mode)
                logger.info("Mission control switched mode to %s", mode)
                return True
            except Exception as exc:
                logger.warning("Failed to set mode '%s': %s", mode, exc)
        return False

    def pause_mission(self) -> bool:
        if not self.vehicle:
            return False
        with self._mission_control_lock:
            self._mission_pause_requested.set()
            self._mission_control_changed.set()
            # Prefer LOITER; BRAKE as fallback where supported.
            return self._set_mode_best_effort("LOITER", "BRAKE")

    def resume_mission(self) -> bool:
        if not self.vehicle:
            return False
        with self._mission_control_lock:
            self._mission_pause_requested.clear()
            self._mission_control_changed.set()
            # Guided mode allows simple_goto waypoint execution to continue.
            return self._set_mode_best_effort("GUIDED", "AUTO")

    def abort_mission(self) -> bool:
        if not self.vehicle:
            return False
        with self._mission_control_lock:
            self._mission_abort_requested.set()
            self._mission_pause_requested.clear()
            self._mission_control_changed.set()
            # RTL first for safe recovery, LAND fallback.
            return self._set_mode_best_effort("RTL", "LAND")

