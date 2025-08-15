from dataclasses import dataclass
from typing import Optional, Dict, Any

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
    armed: bool
    mode: str
    battery_voltage: Optional[float] = None     # Volts
    battery_current: Optional[float] = None     # Amps (+discharge)
    battery_remaining: Optional[float] = None       # Percent (0-100)

@dataclass
class Detection:
    label: str
    confidence: float
    bbox: Optional[tuple] = None  # (x1, y1, x2, y2) in pixels
    extra: Optional[Dict[str, Any]] = None
