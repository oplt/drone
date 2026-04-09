from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Coordinate:
    lat: float
    lon: float
    alt: float = 30.0  # default altitude meters


@dataclass
class LocalCoordinate:
    north_m: float
    east_m: float
    down_m: float
    yaw_deg: float | None = None


@dataclass
class Telemetry:
    lat: float
    lon: float
    alt: float
    heading: float
    groundspeed: float
    # armed: bool
    mode: str
    battery_voltage: float | None = None  # Volts
    battery_current: float | None = None  # Amps (+discharge)
    battery_remaining: float | None = None  # Percent (0-100)
    gps_fix_type: int | None = None
    hdop: float | None = None
    satellites_visible: int | None = None
    heartbeat_age_s: float | None = None
    is_armable: bool | None = None
    home_set: bool | None = None
    home_lat: float | None = None
    home_lon: float | None = None
    ekf_ok: bool | None = None
    local_north_m: float | None = None
    local_east_m: float | None = None
    local_down_m: float | None = None
    local_position_ok: bool | None = None
    local_origin_ok: bool | None = None
    odometry_healthy: bool | None = None
    odometry_drift_m: float | None = None
    lidar_healthy: bool | None = None
    estimator_ready: bool | None = None
    rangefinder_healthy: bool | None = None
    proximity_healthy: bool | None = None
    slam_ready: bool | None = None
    slam_tracking_ok: bool | None = None
    localization_confidence: float | None = None
    dock_reference_ready: bool | None = None
    takeoff_clearance_m: float | None = None
    obstacle_distance_m: float | None = None
    ceiling_distance_m: float | None = None
    system_time: datetime | None = None  # UTC timestamp


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: tuple | None = None  # (x1, y1, x2, y2) in pixels
    extra: dict[str, Any] | None = None
