from __future__ import annotations

import logging
import threading

from backend.core.config.runtime import settings
from backend.infrastructure.vehicle.mavlink.config import (
    WaypointFollowerConfig,
    _sim_or_indoor_home_fallback_allowed,
    logger,
)
from backend.infrastructure.vehicle.mavlink._client_refs import client_module


class MavlinkConnectionMixin:
    """MAVLink connect and home-resolution helpers."""

    def __init__(self, connection_str: str, heartbeat_timeout: float):
        self.connection_str = connection_str
        self.vehicle = None
        self.heartbeat_timeout = heartbeat_timeout
        self.last_heartbeat = client_module().time.time()
        self.dead_mans_switch_active = False
        self.dead_mans_switch_triggered = False
        self.home_location = None
        self.home_source = "unknown"
        self._heartbeat_thread = None
        self._running = False
        self._groundspeed_override_mps = None
        self._capture_mode = None
        self._mission_pause_requested = threading.Event()
        self._mission_abort_requested = threading.Event()
        self._mission_control_changed = threading.Event()
        self._mission_control_lock = threading.Lock()
        self._connect_lock = threading.Lock()
        self._home_fallback_warning_logged = False
        self._warehouse_odometry_overlay: dict[str, object] = {}
        self._warehouse_odometry_overlay_loaded_at = 0.0
        # Segment-follower config; replace or mutate before calling follow_waypoints
        # to tune acceptance radii, lookahead, or attach a progress callback.
        self.follower_config: WaypointFollowerConfig = WaypointFollowerConfig()

    def _resolved_connection_str(self) -> str:
        """Use live runtime settings when the adapter was built with a stale/empty string."""
        configured = (settings.drone_conn or "").strip()
        stored = (self.connection_str or "").strip()
        if configured:
            return configured
        return stored

    def connect(self, *, home_fallback_allowed: bool | None = None) -> None:
        with self._connect_lock:
            if self.vehicle is not None:
                logger.info("MAVLink vehicle already connected endpoint=%s", self.connection_str)
                return
            conn = self._resolved_connection_str()
            if not conn:
                raise RuntimeError(
                    "Drone connection string is not configured. "
                    "Set DRONE_CONN in backend/.env or credentials.drone_conn in Settings."
                )
            self.connection_str = conn
            self.vehicle = client_module().connect(
                self.connection_str,
                wait_ready=True,
                heartbeat_timeout=self.heartbeat_timeout,
            )

        # Wait until autopilot sets home_location (requires GPS fix; often set after arm, but we try early)
        # print("Waiting for home location...")
        logger.info("Waiting for home location...")
        tries = 0
        self._home_fallback_warning_logged = False
        allow_home_fallback = (
            _sim_or_indoor_home_fallback_allowed()
            if home_fallback_allowed is None
            else bool(home_fallback_allowed)
        )
        while not getattr(self.vehicle, "home_location", None) and tries < 30:
            local = getattr(getattr(self.vehicle, "location", None), "local_frame", None)
            if (
                allow_home_fallback
                and local is not None
                and getattr(local, "north", None) is not None
                and getattr(local, "east", None) is not None
            ):
                logger.info(
                    "Local indoor frame is available; proceeding without GPS home "
                    "(simulation/indoor mode)"
                )
                break
            if (
                local is not None
                and getattr(local, "north", None) is not None
                and getattr(local, "east", None) is not None
                and not self._home_fallback_warning_logged
            ):
                logger.warning(
                    "Local frame present but GPS home fallback is disabled for real flight. "
                    "Set SIM_MODE=1 for SITL/local development, or wait for GPS home before "
                    "starting a real flight."
                )
                self._home_fallback_warning_logged = True
            client_module().time.sleep(1)
            tries += 1

        if self.vehicle.home_location:
            self.home_location = self.vehicle.home_location
            self.home_source = "gps_home"
        else:
            # Fallback: use current global frame as a provisional "home"
            loc = self.vehicle.location.global_frame
            if (
                loc is not None
                and getattr(loc, "lat", None) is not None
                and getattr(loc, "lon", None) is not None
            ):
                if not allow_home_fallback:
                    raise RuntimeError(
                        "GPS home is required for real-flight mode; "
                        "simulated home fallback is disabled"
                    )
                self.home_location = loc
                self.home_source = "simulated_home"
            else:
                if not allow_home_fallback:
                    raise RuntimeError(
                        "GPS home is required for real-flight mode; "
                        "local-frame origin fallback is disabled"
                    )
                self.home_location = None
                self.home_source = "local_frame_origin"

        # print(f"Home location set: {self.home_location}")
        logger.info(
            "Home location set source=%s value=%s",
            self.home_source,
            self.home_location,
        )

        """this function and heart beat flow should be added on raspberry pi on drone"""
        # Start the dead man's switch monitoring
        # self.start_dead_mans_switch()

