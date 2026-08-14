from __future__ import annotations

import logging

from pymavlink import mavutil

from backend.infrastructure.vehicle.mavlink._client_refs import client_module
from backend.infrastructure.vehicle.mavlink.config import _mavlink_command_name, logger
from backend.observability.instruments import structured_error
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record


class MavlinkCommandsMixin:
    """MAVLink command_long, groundspeed, and camera capture helpers."""

    def set_groundspeed(self, speed_mps: float) -> bool:
        if not self.vehicle:
            return False
        speed = float(speed_mps)
        if speed <= 0:
            raise ValueError("Groundspeed must be > 0")
        self.vehicle.groundspeed = speed
        self._groundspeed_override_mps = speed
        return True

    def _send_command_long(
        self,
        *,
        command: int,
        p1: float = 0.0,
        p2: float = 0.0,
        p3: float = 0.0,
        p4: float = 0.0,
        p5: float = 0.0,
        p6: float = 0.0,
        p7: float = 0.0,
    ) -> None:
        if not self.vehicle:
            raise RuntimeError("Vehicle not connected")
        command_name = _mavlink_command_name(command)
        started = client_module().time.monotonic()
        with client_module().observed_span(
            "mavlink.command_long",
            drone_id="mavlink",
            mavlink_command=command_name,
            **{
                "mavlink.command.params": (
                    f"p1={p1},p2={p2},p3={p3},p4={p4},p5={p5},p6={p6},p7={p7}"
                ),
                "mavlink.ack.result": "not_waited",
                "mavlink.retry_count": 0,
            },
        ):
            try:
                master = getattr(self.vehicle, "_master", None)
                target_system = int(getattr(master, "target_system", 1) or 1)
                target_component = int(getattr(master, "target_component", 1) or 1)
                msg = self.vehicle.message_factory.command_long_encode(
                    target_system,
                    target_component,
                    int(command),
                    0,  # confirmation
                    float(p1),
                    float(p2),
                    float(p3),
                    float(p4),
                    float(p5),
                    float(p6),
                    float(p7),
                )
                self.vehicle.send_mavlink(msg)
                self.vehicle.flush()
                metric_record(
                    "mavlink_latency",
                    (client_module().time.monotonic() - started) * 1000.0,
                    {"command": command_name, "result": "sent"},
                )
            except Exception as exc:
                metric_add("mavlink_failures", attrs={"command": command_name})
                structured_error(
                    logger,
                    "mavlink_command_failed",
                    exc,
                    mavlink_command=command_name,
                    latency_ms=(client_module().time.monotonic() - started) * 1000.0,
                )
                raise

    def start_image_capture(
        self,
        *,
        mode: str = "distance",
        distance_m: float | None = None,
        interval_s: float | None = None,
    ) -> bool:
        if not self.vehicle:
            return False
        normalized_mode = str(mode or "distance").strip().lower()
        if normalized_mode == "distance":
            dist = float(distance_m or 0.0)
            if dist <= 0:
                raise ValueError("distance_m must be > 0 for distance capture mode")
            self._send_command_long(
                command=mavutil.mavlink.MAV_CMD_DO_SET_CAM_TRIGG_DIST,
                p1=dist,
                p2=0.0,
                p3=0.0,
            )
            self._capture_mode = "distance"
            return True

        if normalized_mode == "time":
            interval = float(interval_s or 0.0)
            if interval <= 0:
                raise ValueError("interval_s must be > 0 for time capture mode")
            self._send_command_long(
                command=mavutil.mavlink.MAV_CMD_IMAGE_START_CAPTURE,
                p1=0.0,  # camera id
                p2=interval,  # capture interval (s)
                p3=0.0,  # 0 => keep capturing until explicit stop
                p4=0.0,
            )
            self._capture_mode = "time"
            return True

        raise ValueError(f"Unsupported image capture mode: {mode!r}")

    def stop_image_capture(self) -> bool:
        if not self.vehicle:
            return False
        sent = False
        try:
            self._send_command_long(
                command=mavutil.mavlink.MAV_CMD_IMAGE_STOP_CAPTURE,
                p1=0.0,
            )
            sent = True
        except Exception as exc:
            logger.warning("Failed to send MAV_CMD_IMAGE_STOP_CAPTURE: %s", exc)

        try:
            self._send_command_long(
                command=mavutil.mavlink.MAV_CMD_DO_SET_CAM_TRIGG_DIST,
                p1=0.0,
            )
            sent = True
        except Exception as exc:
            logger.warning("Failed to disable MAV_CMD_DO_SET_CAM_TRIGG_DIST: %s", exc)

        self._capture_mode = None
        return sent

    def start_video_recording(self) -> bool:
        if not self.vehicle:
            return False

        command = getattr(mavutil.mavlink, "MAV_CMD_VIDEO_START_CAPTURE", None)
        if command is None:
            logger.warning("MAV_CMD_VIDEO_START_CAPTURE is unavailable in this pymavlink build")
            return False

        try:
            self._send_command_long(
                command=command,
                p1=0.0,  # camera id: all/default camera
                p2=1.0,  # status frequency in Hz
                p3=0.0,
                p4=0.0,
            )
            return True
        except Exception as exc:
            logger.warning("Failed to send MAV_CMD_VIDEO_START_CAPTURE: %s", exc)
            return False

    def stop_video_recording(self) -> bool:
        if not self.vehicle:
            return False

        command = getattr(mavutil.mavlink, "MAV_CMD_VIDEO_STOP_CAPTURE", None)
        if command is None:
            logger.warning("MAV_CMD_VIDEO_STOP_CAPTURE is unavailable in this pymavlink build")
            return False

        try:
            self._send_command_long(
                command=command,
                p1=0.0,  # camera id: all/default camera
            )
            return True
        except Exception as exc:
            logger.warning("Failed to send MAV_CMD_VIDEO_STOP_CAPTURE: %s", exc)
            return False

    def download_captured_images(self, *, destination_dir: str) -> list[str]:
        # DroneKit+MAVLink path in this adapter does not expose camera file transfer.
        # A companion sync process should populate destination_dir instead.
        logger.info(
            "Direct camera image download is unsupported by MavlinkDrone adapter; "
            "destination_dir=%s",
            destination_dir,
        )
        return []

