from __future__ import annotations

import asyncio
import logging
import shlex
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.warehouse.bridge_config import ros_command_env
from backend.modules.warehouse.models import WarehouseCoordinateFrame
from backend.modules.warehouse.service.coordinate_frames import validate_transform
from backend.modules.warehouse.service.sim_time_tf_readiness import (
    _ros_distro_setup_path,
    _ros_workspace,
)

logger = logging.getLogger(__name__)

MAP_TO_ODOM_TOPIC = "/warehouse/localization/map_to_odom"
MAP_TO_ODOM_MSG = "geometry_msgs/msg/TransformStamped"


def transform_stamped_yaml(transform: dict[str, Any]) -> str:
    validated = validate_transform(transform)
    translation = validated["translation"]
    rotation = validated["rotation"]
    return (
        "header:\n"
        "  frame_id: warehouse_map\n"
        "child_frame_id: odom\n"
        "transform:\n"
        f"  translation:\n"
        f"    x: {translation['x']}\n"
        f"    y: {translation['y']}\n"
        f"    z: {translation['z']}\n"
        f"  rotation:\n"
        f"    x: {rotation['x']}\n"
        f"    y: {rotation['y']}\n"
        f"    z: {rotation['z']}\n"
        f"    w: {rotation['w']}\n"
    )


def _sourced_ros_cmd(inner: str) -> list[str]:
    ws = _ros_workspace()
    setup = ws / "install" / "setup.bash"
    script_parts = [f"source {shlex.quote(_ros_distro_setup_path())}"]
    if setup.exists():
        script_parts.append(f"source {shlex.quote(str(setup))}")
    script_parts.append(inner)
    return ["bash", "-lc", " && ".join(script_parts)]


async def publish_map_to_odom_transform(transform: dict[str, Any]) -> tuple[bool, str]:
    """Push a locked warehouse_map -> odom transform to the ROS localization topic."""
    yaml_payload = transform_stamped_yaml(transform)
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(yaml_payload)
            yaml_path = Path(handle.name)
        try:
            result = await asyncio.to_thread(
                __import__("subprocess").run,
                _sourced_ros_cmd(
                    "timeout 8 ros2 topic pub --once "
                    f"{shlex.quote(MAP_TO_ODOM_TOPIC)} {MAP_TO_ODOM_MSG} "
                    f"-f {shlex.quote(str(yaml_path))}"
                ),
                env=ros_command_env(),
                capture_output=True,
                text=True,
                timeout=12.0,
                check=False,
            )
        finally:
            yaml_path.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Failed to publish warehouse_map->odom transform", exc_info=True)
        return False, str(exc)

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "ros2 topic pub failed").strip()[:240]
        logger.warning("ROS map_to_odom publish failed: %s", detail)
        return False, detail
    return True, "Published warehouse_map->odom localization transform"


async def sync_locked_coordinate_frame_to_ros(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
) -> tuple[bool, str]:
    row = (
        await db.execute(
            select(WarehouseCoordinateFrame)
            .where(
                WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id,
                WarehouseCoordinateFrame.status == "locked",
            )
            .order_by(WarehouseCoordinateFrame.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return False, "No locked coordinate frame to sync"
    return await publish_map_to_odom_transform(row.transform_json)
