# ruff: noqa: E402,I001
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BRIDGE_SRC = ROOT / "jetson_ros2_ws" / "src" / "warehouse_mapping_bridge"
if str(BRIDGE_SRC) not in sys.path:
    sys.path.insert(0, str(BRIDGE_SRC))

from backend.core.config.runtime import settings
from backend.infrastructure.vehicle.mavlink_client import MavlinkDrone
from warehouse_mapping_bridge.vision_mavlink import odometry_to_vision_pose


def test_odometry_to_vision_pose_converts_enu_to_ned() -> None:
    message = SimpleNamespace(
        pose=SimpleNamespace(
            pose=SimpleNamespace(
                position=SimpleNamespace(x=2.0, y=3.0, z=1.5),
                orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
            )
        )
    )

    estimate = odometry_to_vision_pose(message, now_usec=123)

    assert estimate.usec == 123
    assert estimate.x_north_m == 3.0
    assert estimate.y_east_m == 2.0
    assert estimate.z_down_m == -1.5
    assert estimate.roll_rad == 0.0
    assert estimate.pitch_rad == 0.0
    assert estimate.yaw_rad == 0.0
    assert len(estimate.covariance) == 21


def test_mavlink_drone_telemetry_uses_warehouse_odometry_overlay(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    state_path = tmp_path / "latest_odometry.json"
    state_path.write_text(
        json.dumps(
            {
                "local_north_m": 4.0,
                "local_east_m": 5.0,
                "local_down_m": -1.2,
                "local_position_ok": True,
                "slam_ready": True,
                "slam_tracking_ok": True,
                "localization_confidence": 0.91,
                "odometry_drift_m": 0.12,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "WAREHOUSE_ODOMETRY_STATE_PATH", str(state_path))

    drone = MavlinkDrone("udp:127.0.0.1:14550", heartbeat_timeout=1.0)
    drone.vehicle = SimpleNamespace(
        location=SimpleNamespace(
            global_relative_frame=SimpleNamespace(lat=None, lon=None, alt=None),
            global_frame=SimpleNamespace(lat=None, lon=None, alt=None),
            local_frame=SimpleNamespace(north=None, east=None, down=None),
        ),
        battery=SimpleNamespace(voltage=15.0, current=1.0, level=88),
        gps_0=SimpleNamespace(fix_type=0, eph=None, satellites_visible=0),
        home_location=None,
        heading=0,
        groundspeed=0.0,
        mode=SimpleNamespace(name="GUIDED"),
        last_heartbeat=0.1,
        is_armable=True,
        ekf_ok=True,
        rangefinder=SimpleNamespace(distance=2.5),
    )

    telemetry = drone.get_telemetry()

    assert telemetry.local_north_m == 4.0
    assert telemetry.local_east_m == 5.0
    assert math.isclose(telemetry.local_down_m or 0.0, -1.2)
    assert telemetry.local_position_ok is True
    assert telemetry.slam_ready is True
    assert telemetry.slam_tracking_ok is True
    assert telemetry.localization_confidence == 0.91
    assert telemetry.odometry_drift_m == 0.12
