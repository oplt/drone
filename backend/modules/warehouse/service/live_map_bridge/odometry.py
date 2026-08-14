"""Warehouse live-map bridge — odometry pose parsing."""

from __future__ import annotations

import logging
import math
from pathlib import Path

from backend.infrastructure.warehouse.bridge_config import load_bridge_config
from backend.modules.warehouse.service.live_map_stream import WarehouseLivePose
from backend.modules.warehouse.service.map_source_config import WAREHOUSE_LIVE_MAP_SOURCES

from .constants import _POSITION_RE, _YAW_RE
from .ros_commands import _run_ros2_command
from .workspace import _ros2_workspace

logger = logging.getLogger(__name__)


def _odometry_topic() -> str:
    configured = WAREHOUSE_LIVE_MAP_SOURCES["odom"].topic
    ws = _ros2_workspace()
    try:
        mappings = load_bridge_config(ws)
        for entry in mappings:
            if entry.ros_type_name == "nav_msgs/msg/Odometry":
                topic = str(entry.ros_topic_name or "").strip()
                if topic:
                    return topic
    except Exception:
        logger.debug("Could not load warehouse bridge config from %s", ws, exc_info=True)
    return configured


def _quat_to_yaw_deg(x: float, y: float, z: float, w: float) -> float:
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.degrees(math.atan2(siny_cosp, cosy_cosp))


def _parse_odometry_echo(stdout: str) -> WarehouseLivePose | None:
    pos = _POSITION_RE.search(stdout)
    if not pos:
        return None

    try:
        x_m = float(pos.group(1))
        y_m = float(pos.group(2))
        z_m = float(pos.group(3))
    except (TypeError, ValueError):
        return None

    yaw_deg: float | None = None
    orient = _YAW_RE.search(stdout)
    if orient:
        try:
            yaw_deg = round(
                _quat_to_yaw_deg(
                    float(orient.group(1)),
                    float(orient.group(2)),
                    float(orient.group(3)),
                    float(orient.group(4)),
                ),
                2,
            )
        except (TypeError, ValueError):
            yaw_deg = None

    return WarehouseLivePose(
        x_m=x_m,
        y_m=y_m,
        z_m=z_m,
        yaw_deg=yaw_deg,
        frame_id="odom",
    )


def _read_odometry_pose(*, topic: str, ws: Path) -> WarehouseLivePose | None:
    result = _run_ros2_command(
        ws=ws,
        ros_args=("topic", "echo", topic, "--once"),
        shell_timeout_s=2.0,
        process_timeout_s=5.0,
    )
    if result is None:
        return None
    if result.returncode != 0 and not result.stdout.strip():
        return None
    return _parse_odometry_echo(result.stdout)


__all__ = ["_odometry_topic", "_read_odometry_pose"]
