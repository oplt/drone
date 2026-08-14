from __future__ import annotations

DEFAULT_LAST_TELEMETRY: dict = {
    "position": {"lat": 0, "lon": 0, "alt": 0, "relative_alt": 0},
    "attitude": {"roll": 0, "pitch": 0, "yaw": 0},
    "battery": {"voltage": 0, "current": 0, "remaining": 0, "temperature": 0},
    "gps": {"satellites": 0, "hdop": None},
    "link": {"rc": None, "lte": None, "telemetry": None},
    "wind": {"speed": 0, "direction": 0},
    "failsafe": {"state": "Normal"},
    "system": {"status": "UNKNOWN"},
    "status": {
        "groundspeed": 0,
        "airspeed": 0,
        "heading": 0,
        "throttle": 0,
        "climb": 0,
    },
    "camera": {"gimbal_pitch_deg": None},
    "mode": "DISCONNECTED",
    "armed": False,
    "timestamp": 0,
}
