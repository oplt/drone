from __future__ import annotations

import logging
import math

from pymavlink import mavutil

from backend.infrastructure.vehicle.frame_conversion import enu_to_local_ned
from backend.infrastructure.vehicle.mavlink._client_refs import client_module
from backend.infrastructure.vehicle.mavlink.config import logger
from backend.modules.vehicle_runtime.types import EnuCoordinate, LocalCoordinate
from backend.modules.vehicle_runtime.vehicle_port import MissionAbortRequested
from backend.observability.instruments import structured_error
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record


class MavlinkLocalControlMixin:
    """Local NED / ENU setpoint and velocity control."""

    def _send_local_position_target(self, coord: LocalCoordinate) -> None:
        if not self.vehicle:
            raise RuntimeError("Vehicle not connected")

        master = getattr(self.vehicle, "_master", None)
        target_system = int(getattr(master, "target_system", 1) or 1)
        target_component = int(getattr(master, "target_component", 1) or 1)
        type_mask = (
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_VX_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VY_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VZ_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AX_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AY_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AZ_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE
        )
        yaw_rad = 0.0
        if coord.yaw_rad is None:
            type_mask |= mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_IGNORE
        else:
            yaw_rad = float(coord.yaw_rad)

        msg = self.vehicle.message_factory.set_position_target_local_ned_encode(
            0,
            target_system,
            target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            int(type_mask),
            float(coord.north_m),
            float(coord.east_m),
            float(coord.down_m),
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            float(yaw_rad),
            0.0,
        )
        self.vehicle.send_mavlink(msg)
        self.vehicle.flush()

    def send_velocity(
        self,
        vx: float,
        vy: float,
        vz: float,
        yaw_rate_dps: float = 0.0,
    ) -> None:
        """Send NED velocity setpoint via SET_POSITION_TARGET_LOCAL_NED."""
        if not self.vehicle:
            raise RuntimeError("Vehicle not connected")
        started = client_module().time.monotonic()
        with client_module().observed_span(
            "mavlink.set_velocity",
            drone_id="mavlink",
            mavlink_command="set_velocity",
            **{"mavlink.ack.result": "not_waited", "mavlink.retry_count": 0},
        ):
            try:
                master = getattr(self.vehicle, "_master", None)
                target_system = int(getattr(master, "target_system", 1) or 1)
                target_component = int(getattr(master, "target_component", 1) or 1)

                type_mask = (
                    mavutil.mavlink.POSITION_TARGET_TYPEMASK_X_IGNORE
                    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_Y_IGNORE
                    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_Z_IGNORE
                    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AX_IGNORE
                    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AY_IGNORE
                    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AZ_IGNORE
                    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_IGNORE
                )

                msg = self.vehicle.message_factory.set_position_target_local_ned_encode(
                    0,
                    target_system,
                    target_component,
                    mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                    int(type_mask),
                    0.0,
                    0.0,
                    0.0,
                    float(vx),
                    float(vy),
                    float(vz),
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    math.radians(float(yaw_rate_dps)),
                )
                self.vehicle.send_mavlink(msg)
                self.vehicle.flush()
                metric_record(
                    "mavlink_latency",
                    (client_module().time.monotonic() - started) * 1000.0,
                    {"command": "set_velocity", "result": "sent"},
                )
            except Exception as exc:
                metric_add("mavlink_failures", attrs={"command": "set_velocity"})
                structured_error(
                    logger,
                    "mavlink_command_failed",
                    exc,
                    mavlink_command="set_velocity",
                    latency_ms=(client_module().time.monotonic() - started) * 1000.0,
                )
                raise

    def _local_distance_to_target(self, coord: LocalCoordinate) -> float:
        if not self.vehicle:
            raise RuntimeError("Vehicle not connected")
        local = getattr(getattr(self.vehicle, "location", None), "local_frame", None)
        if local is None:
            raise RuntimeError("Vehicle local frame is not available")
        north = getattr(local, "north", None)
        east = getattr(local, "east", None)
        down = getattr(local, "down", None)
        if north is None or east is None or down is None:
            raise RuntimeError("Vehicle local position is incomplete")
        return math.sqrt(
            (float(north) - float(coord.north_m)) ** 2
            + (float(east) - float(coord.east_m)) ** 2
            + (float(down) - float(coord.down_m)) ** 2
        )

    def follow_local_setpoints(self, path):
        self._mission_abort_requested.clear()
        self._mission_pause_requested.clear()
        for coord in path:
            self._send_local_position_target(coord)

            start_time = client_module().time.monotonic()
            paused_started_at = None
            paused_total_s = 0.0
            was_paused = False
            max_active_leg_s = 180.0
            while True:
                if self._mission_abort_requested.is_set():
                    raise MissionAbortRequested("Operator abort requested")

                if self._mission_pause_requested.is_set():
                    if paused_started_at is None:
                        paused_started_at = client_module().time.monotonic()
                        was_paused = True
                    self._mission_control_changed.wait(timeout=0.2)
                    self._mission_control_changed.clear()
                    continue

                if paused_started_at is not None:
                    paused_total_s += client_module().time.monotonic() - paused_started_at
                    paused_started_at = None
                if was_paused:
                    self._send_local_position_target(coord)
                    was_paused = False

                distance = self._local_distance_to_target(coord)
                if distance < 0.8:
                    break

                active_elapsed_s = (client_module().time.monotonic() - start_time) - paused_total_s
                if active_elapsed_s > max_active_leg_s:
                    raise RuntimeError(
                        f"Local setpoint leg timeout after {max_active_leg_s:.0f}s active flight time"
                    )

                self._mission_control_changed.wait(timeout=0.2)
                self._mission_control_changed.clear()

    def follow_enu_setpoints(self, path: list[EnuCoordinate], timeout_s: float | None = None):
        """Only warehouse-facing local control API; conversion occurs at MAVLink boundary."""
        del timeout_s
        self.follow_local_setpoints([enu_to_local_ned(coord) for coord in path])

