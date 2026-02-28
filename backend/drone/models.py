from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class Coordinate:
    lat: float
    lon: float
    alt: float = 30.0  # default altitude meters


@dataclass
class Telemetry:
    lat: float
    lon: float
    alt: float
    heading: float
    groundspeed: float
    # armed: bool
    mode: str
    battery_voltage: Optional[float] = None  # Volts
    battery_current: Optional[float] = None  # Amps (+discharge)
    battery_remaining: Optional[float] = None  # Percent (0-100)
    gps_fix_type: Optional[int] = None
    hdop: Optional[float] = None
    satellites_visible: Optional[int] = None
    heartbeat_age_s: Optional[float] = None
    is_armable: Optional[bool] = None
    home_set: Optional[bool] = None
    home_lat: Optional[float] = None
    home_lon: Optional[float] = None
    ekf_ok: Optional[bool] = None
    system_time: Optional[datetime] = None  # UTC timestamp


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: Optional[tuple] = None  # (x1, y1, x2, y2) in pixels
    extra: Optional[Dict[str, Any]] = None
