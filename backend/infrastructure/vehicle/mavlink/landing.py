from __future__ import annotations

import logging

from dronekit import VehicleMode

from backend.infrastructure.vehicle.mavlink._client_refs import client_module
from backend.infrastructure.vehicle.mavlink.config import logger


class MavlinkLandingMixin:
    """Land, disarm wait, distance helpers, and lifecycle cleanup."""

    def _distance_to_target(self, current_loc, target_coord):
        """Calculate distance to target coordinate"""
        from math import atan2, cos, radians, sin, sqrt

        # Haversine formula for distance
        R = 6371000  # Earth's radius in meters

        lat1, lon1 = radians(current_loc.lat), radians(current_loc.lon)
        lat2, lon2 = radians(target_coord.lat), radians(target_coord.lon)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return R * c

    def land(self) -> None:
        # self.send_heartbeat()
        self.vehicle.mode = VehicleMode("LAND")

    def wait_until_disarmed(self, timeout_s: float = 900):
        """Block until vehicle.armed == False or raise TimeoutError."""
        start = client_module().time.time()
        while (client_module().time.time() - start) < timeout_s:
            if self.vehicle is None:
                raise RuntimeError("Vehicle unavailable while waiting for disarm")

            if not getattr(self.vehicle, "armed", False):
                return

            # self.send_heartbeat()  # keeps dead-man switch happy
            client_module().time.sleep(1.0)

        if self.vehicle is not None and getattr(self.vehicle, "armed", False):
            mode = getattr(getattr(self.vehicle, "mode", None), "name", None)
            raise TimeoutError(
                f"Timed out after {timeout_s}s waiting for disarm (mode={mode or 'unknown'})"
            )

    def stop_dead_mans_switch(self):
        """Safely disable the dead man's switch"""
        # print("Stopping dead man's switch...")
        logger.info("Stopping dead man's switch...")
        self._running = False
        self.dead_mans_switch_active = False

        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)

    def close(self) -> None:
        self.stop_dead_mans_switch()
        if self.vehicle:
            self.vehicle.close()

