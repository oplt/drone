from __future__ import annotations

import logging

from backend.infrastructure.vehicle.mavlink.config import logger
from backend.modules.vehicle_runtime.types import Telemetry


class MavlinkTelemetryMixin:
    """Telemetry assembly from DroneKit vehicle state."""

    def get_telemetry(self) -> Telemetry:
        # Send heartbeat when getting telemetry (this happens regularly)
        # self.send_heartbeat()

        v = self.vehicle
        if v is None:
            raise RuntimeError("Vehicle not connected yet")

        loc = getattr(v, "location", None)
        rel = getattr(loc, "global_relative_frame", None)
        glob = getattr(loc, "global_frame", None)
        local = getattr(loc, "local_frame", None)
        bat = getattr(v, "battery", None)
        gps = getattr(v, "gps_0", None)
        home = getattr(v, "home_location", None) or self.home_location
        local_north = getattr(local, "north", None)
        local_east = getattr(local, "east", None)
        local_down = getattr(local, "down", None)
        overlay = self._load_warehouse_odometry_overlay()
        overlay_north = self._overlay_float(overlay, "local_north_m")
        overlay_east = self._overlay_float(overlay, "local_east_m")
        overlay_down = self._overlay_float(overlay, "local_down_m")
        if local_north is None:
            local_north = overlay_north
        if local_east is None:
            local_east = overlay_east
        if local_down is None:
            local_down = overlay_down
        local_position_ok = (
            local_north is not None and local_east is not None and local_down is not None
        )
        overlay_local_ok = self._overlay_bool(overlay, "local_position_ok")
        if overlay_local_ok is not None:
            local_position_ok = local_position_ok and overlay_local_ok
        rangefinder = getattr(v, "rangefinder", None)
        obstacle_distance = getattr(rangefinder, "distance", None)
        lat = getattr(rel, "lat", None) if rel is not None else None
        lon = getattr(rel, "lon", None) if rel is not None else None
        alt = getattr(rel, "alt", None) if rel is not None else None
        if lat is None:
            lat = getattr(glob, "lat", None)
        if lon is None:
            lon = getattr(glob, "lon", None)
        if alt is None:
            alt = getattr(glob, "alt", None)
        if alt is None and local_down is not None:
            alt = -float(local_down)
        home_lat = getattr(home, "lat", None) if home is not None else None
        home_lon = getattr(home, "lon", None) if home is not None else None
        if lat is None:
            lat = home_lat if home_lat is not None else 0.0
        if lon is None:
            lon = home_lon if home_lon is not None else 0.0
        if alt is None:
            alt = 0.0
        if home_lat is None or home_lon is None:
            home_set = None if local_position_ok else False
        else:
            home_set = True
        heading = getattr(v, "heading", None)
        groundspeed = getattr(v, "groundspeed", None)
        mode_name = getattr(getattr(v, "mode", None), "name", None) or "UNKNOWN"
        return Telemetry(
            lat=float(lat),
            lon=float(lon),
            alt=float(alt),
            heading=float(heading) if heading is not None else 0.0,
            groundspeed=float(groundspeed) if groundspeed is not None else 0.0,
            mode=str(mode_name),
            battery_voltage=getattr(bat, "voltage", None),
            battery_current=getattr(bat, "current", None),
            battery_remaining=getattr(bat, "level", None),
            gps_fix_type=getattr(gps, "fix_type", None),
            hdop=getattr(gps, "eph", None),
            satellites_visible=getattr(gps, "satellites_visible", None),
            heartbeat_age_s=getattr(v, "last_heartbeat", None),
            is_armable=getattr(v, "is_armable", None),
            home_set=home_set,
            home_source=self.home_source,
            home_lat=home_lat,
            home_lon=home_lon,
            ekf_ok=getattr(v, "ekf_ok", None),
            local_north_m=float(local_north) if local_north is not None else None,
            local_east_m=float(local_east) if local_east is not None else None,
            local_down_m=float(local_down) if local_down is not None else None,
            local_position_ok=local_position_ok,
            local_origin_ok=local_position_ok or home_set is True,
            odometry_healthy=self._overlay_bool(overlay, "slam_tracking_ok")
            if self._overlay_bool(overlay, "slam_tracking_ok") is not None
            else local_position_ok,
            odometry_drift_m=self._overlay_float(overlay, "odometry_drift_m"),
            lidar_healthy=(
                bool(obstacle_distance > 0.0) if obstacle_distance is not None else None
            ),
            obstacle_distance_m=(
                float(obstacle_distance) if obstacle_distance is not None else None
            ),
            ceiling_distance_m=None,
            slam_ready=self._overlay_bool(overlay, "slam_ready"),
            slam_tracking_ok=self._overlay_bool(overlay, "slam_tracking_ok"),
            localization_confidence=self._overlay_float(overlay, "localization_confidence"),
        )

