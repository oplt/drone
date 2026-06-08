from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import struct
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from backend.core.config.runtime import env_truthy, settings
from backend.infrastructure.warehouse.bridge_config import (
    bridge_config_path,
    list_ros2_topics,
    load_bridge_config,
    ros_command_env,
)
from backend.modules.warehouse.service.live_map_storage import (
    warehouse_live_map_chunk_storage,
)
from backend.modules.warehouse.service.live_map_stream import (
    WarehouseLiveHealthFlags,
    WarehouseLivePose,
    normalize_live_map_payload,
    warehouse_live_map_stream,
)

logger = logging.getLogger(__name__)

_POSITION_RE = re.compile(
    r"position:\s*\n\s*x:\s*([-+0-9.eE]+)\s*\n\s*y:\s*([-+0-9.eE]+)\s*\n\s*z:\s*([-+0-9.eE]+)",
    re.MULTILINE,
)
_YAW_RE = re.compile(
    r"orientation:\s*\n\s*x:\s*([-+0-9.eE]+)\s*\n\s*y:\s*([-+0-9.eE]+)\s*\n\s*z:\s*([-+0-9.eE]+)\s*\n\s*w:\s*([-+0-9.eE]+)",
    re.MULTILINE,
)

_bridge_task: asyncio.Task[None] | None = None
_bridge_flight_id: str | None = None
_bridge_stop: asyncio.Event | None = None


def _ros2_workspace() -> Path:
    raw = settings.warehouse_ros2_ws.strip() or "ros2_ws"
    return Path(raw).expanduser().resolve()


def _odometry_topic() -> str:
    ws = _ros2_workspace()
    try:
        mappings = load_bridge_config(ws)
        for entry in mappings:
            if entry.ros_type_name == "nav_msgs/msg/Odometry":
                topic = str(entry.ros_topic_name or "").strip()
                if topic:
                    return topic
    except Exception:
        pass
    return "/warehouse/drone/odometry"


def _esdf_topic() -> str:
    from backend.modules.warehouse.service.bridge_flow import resolve_warehouse_bridge_flow

    flow = resolve_warehouse_bridge_flow()
    configured = settings.warehouse_esdf_topic.strip()
    if configured:
        return configured
    return (
        "/nvblox_node/static_esdf_pointcloud"
        if flow.gazebo_sim
        else "/warehouse/contract/map/esdf"
    )


def _quat_to_yaw_deg(x: float, y: float, z: float, w: float) -> float:
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.degrees(math.atan2(siny_cosp, cosy_cosp))


def _parse_odometry_echo(stdout: str) -> WarehouseLivePose | None:
    pos = _POSITION_RE.search(stdout)
    if not pos:
        return None

    x_m = float(pos.group(1))
    y_m = float(pos.group(2))
    z_m = float(pos.group(3))

    yaw_deg: float | None = None
    orient = _YAW_RE.search(stdout)
    if orient:
        yaw_deg = round(
            _quat_to_yaw_deg(
                float(orient.group(1)),
                float(orient.group(2)),
                float(orient.group(3)),
                float(orient.group(4)),
            ),
            2,
        )

    return WarehouseLivePose(
        x_m=x_m,
        y_m=y_m,
        z_m=z_m,
        yaw_deg=yaw_deg,
        frame_id="odom",
    )


def _read_odometry_pose(*, topic: str, ws: Path) -> WarehouseLivePose | None:
    cmd = (
        f"source /opt/ros/${{ROS_DISTRO:-jazzy}}/setup.bash && "
        f"source {ws / 'install/setup.bash'} && "
        f"timeout 2 ros2 topic echo {topic} --once"
    )
    try:
        result = subprocess.run(
            ["bash", "-lc", cmd],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
            env=ros_command_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0 and not result.stdout.strip():
        return None

    return _parse_odometry_echo(result.stdout)


def _nvblox_ready(*, ws: Path, esdf_topic: str) -> bool:
    try:
        topics = list_ros2_topics(ws)
    except RuntimeError:
        return False

    if esdf_topic in topics:
        return True

    return any(str(topic).startswith("/nvblox_node/") for topic in topics)


def _read_pointcloud2_yaml(*, topic: str, ws: Path) -> dict[str, Any] | None:
    """
    Development bridge: reads one PointCloud2 sample via ROS CLI and parses YAML.

    This is intentionally a minimal bridge to prove the UI data path:
      /nvblox_node/static_esdf_pointcloud -> changed_chunks -> frontend.

    Later, replace this with a persistent rclpy subscriber for performance.
    """
    cmd = (
        f"source /opt/ros/${{ROS_DISTRO:-jazzy}}/setup.bash && "
        f"source {ws / 'install/setup.bash'} && "
        f"timeout 2 ros2 topic echo {topic} --once --full-length"
    )
    try:
        result = subprocess.run(
            ["bash", "-lc", cmd],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=4.0,
            check=False,
            env=ros_command_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0 or not result.stdout.strip():
        return None

    try:
        # `ros2 topic echo` appends a trailing `---` document marker; safe_load()
        # rejects that as a second document and would drop every ESDF chunk.
        payload = next(
            (
                doc
                for doc in yaml.safe_load_all(result.stdout)
                if isinstance(doc, dict)
            ),
            None,
        )
    except Exception:
        logger.debug("Could not parse PointCloud2 YAML from %s", topic, exc_info=True)
        return None

    return payload


_POINTFIELD_DATATYPE_SIZE: dict[int, int] = {
    1: 1,  # INT8
    2: 1,  # UINT8
    3: 2,  # INT16
    4: 2,  # UINT16
    5: 4,  # INT32
    6: 4,  # UINT32
    7: 4,  # FLOAT32
    8: 8,  # FLOAT64
}


def _unpack_field(
        raw: bytes,
        *,
        offset: int,
        datatype: int,
        little_endian: bool,
) -> float | None:
    prefix = "<" if little_endian else ">"

    try:
        if datatype == 1:
            return float(struct.unpack_from(prefix + "b", raw, offset)[0])
        if datatype == 2:
            return float(struct.unpack_from(prefix + "B", raw, offset)[0])
        if datatype == 3:
            return float(struct.unpack_from(prefix + "h", raw, offset)[0])
        if datatype == 4:
            return float(struct.unpack_from(prefix + "H", raw, offset)[0])
        if datatype == 5:
            return float(struct.unpack_from(prefix + "i", raw, offset)[0])
        if datatype == 6:
            return float(struct.unpack_from(prefix + "I", raw, offset)[0])
        if datatype == 7:
            return float(struct.unpack_from(prefix + "f", raw, offset)[0])
        if datatype == 8:
            return float(struct.unpack_from(prefix + "d", raw, offset)[0])
    except (struct.error, ValueError):
        return None

    return None


def _pointcloud2_to_chunk(
        payload: dict[str, Any],
        *,
        flight_id: str,
        sequence: int,
        max_points: int,
) -> dict[str, Any] | None:
    fields = payload.get("fields")
    data = payload.get("data")
    point_step_raw = payload.get("point_step")
    is_bigendian = bool(payload.get("is_bigendian", False))

    if not isinstance(fields, list) or not isinstance(data, list):
        return None

    try:
        point_step = int(point_step_raw)
    except (TypeError, ValueError):
        return None

    if point_step <= 0:
        return None

    field_by_name: dict[str, dict[str, Any]] = {}
    for field in fields:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "")
        if name:
            field_by_name[name] = field

    required = ["x", "y", "z"]
    if not all(name in field_by_name for name in required):
        return None

    try:
        raw = bytes(int(value) & 0xFF for value in data)
    except (TypeError, ValueError):
        return None

    total_points = len(raw) // point_step
    if total_points <= 0:
        return None

    stride = max(1, total_points // max(1, max_points))
    little_endian = not is_bigendian

    x_field = field_by_name["x"]
    y_field = field_by_name["y"]
    z_field = field_by_name["z"]

    try:
        x_offset = int(x_field["offset"])
        y_offset = int(y_field["offset"])
        z_offset = int(z_field["offset"])
        x_type = int(x_field["datatype"])
        y_type = int(y_field["datatype"])
        z_type = int(z_field["datatype"])
    except (KeyError, TypeError, ValueError):
        return None

    sampled: list[list[float]] = []
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")

    for index in range(0, total_points, stride):
        base = index * point_step

        x = _unpack_field(raw, offset=base + x_offset, datatype=x_type, little_endian=little_endian)
        y = _unpack_field(raw, offset=base + y_offset, datatype=y_type, little_endian=little_endian)
        z = _unpack_field(raw, offset=base + z_offset, datatype=z_type, little_endian=little_endian)

        if x is None or y is None or z is None:
            continue
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
            continue

        sampled.append([round(x, 3), round(y, 3), round(z, 3)])

        min_x = min(min_x, x)
        min_y = min(min_y, y)
        min_z = min(min_z, z)
        max_x = max(max_x, x)
        max_y = max(max_y, y)
        max_z = max(max_z, z)

        if len(sampled) >= max_points:
            break

    if not sampled:
        return None

    # The frontend currently uses chunk metadata for rendering.
    # `preview_points` is included for the next frontend upgrade; existing Pydantic
    # models may ignore it, but it is harmless if extra fields are allowed.
    chunk_payload = {
        "format": "xyz_preview_v1",
        "frame_id": str((payload.get("header") or {}).get("frame_id") or "odom"),
        "source_topic": "/nvblox_node/static_esdf_pointcloud",
        "sampled_point_count": len(sampled),
        "source_point_count": total_points,
        "points": sampled,
    }
    chunk_json = json.dumps(chunk_payload, separators=(",", ":")).encode("utf-8")

    return {
        "id": f"nvblox_esdf_{sequence:08d}",
        "kind": "point_cloud",
        "sequence": sequence,
        "point_count": total_points,
        "byte_size": len(chunk_json),
        "content_type": "application/json",
        "bbox_local_m": [
            round(min_x, 3),
            round(min_y, 3),
            round(min_z, 3),
            round(max_x, 3),
            round(max_y, 3),
            round(max_z, 3),
        ],
        "preview_points_m": sampled,
    }


def _read_nvblox_chunk(
        *,
        flight_id: str,
        topic: str,
        ws: Path,
        sequence: int,
) -> dict[str, Any] | None:
    payload = _read_pointcloud2_yaml(topic=topic, ws=ws)
    if payload is None:
        return None

    max_points = settings.warehouse_live_map_max_preview_points
    return _pointcloud2_to_chunk(
        payload,
        flight_id=flight_id,
        sequence=sequence,
        max_points=max(100, max_points),
    )


async def _publish_loop(flight_id: str, stop: asyncio.Event) -> None:
    ws = _ros2_workspace()
    odom_topic = _odometry_topic()
    esdf_topic = _esdf_topic()
    poll_s = settings.warehouse_live_map_poll_s
    pointcloud_every_n = max(1, settings.warehouse_live_map_pointcloud_every_n)

    sequence = 0
    chunk_failures = 0

    logger.info(
        "Warehouse live map bridge started flight_id=%s odom=%s esdf=%s config=%s",
        flight_id,
        odom_topic,
        esdf_topic,
        bridge_config_path(ws),
    )

    while not stop.is_set():
        sequence += 1

        pose = await asyncio.to_thread(_read_odometry_pose, topic=odom_topic, ws=ws)
        nvblox_ok = await asyncio.to_thread(_nvblox_ready, ws=ws, esdf_topic=esdf_topic)

        changed_chunks: list[dict[str, Any]] = []
        if nvblox_ok and sequence % pointcloud_every_n == 0:
            chunk = await asyncio.to_thread(
                _read_nvblox_chunk,
                flight_id=flight_id,
                topic=esdf_topic,
                ws=ws,
                sequence=sequence,
            )
            if chunk is not None:
                changed_chunks.append(chunk)
                chunk_failures = 0
                try:
                    preview_points = chunk.get("preview_points_m")
                    if isinstance(preview_points, list) and preview_points:
                        await asyncio.to_thread(
                            warehouse_live_map_chunk_storage.save_preview_chunk,
                            flight_id=flight_id,
                            chunk_id=str(chunk["id"]),
                            preview_points_m=preview_points,
                            point_count=chunk.get("point_count"),
                            bbox_local_m=chunk.get("bbox_local_m"),
                            sequence=int(chunk.get("sequence") or sequence),
                        )
                except Exception:
                    logger.warning(
                        "Failed to persist nvblox preview chunk flight_id=%s chunk_id=%s",
                        flight_id,
                        chunk.get("id"),
                        exc_info=True,
                    )
            else:
                chunk_failures += 1
                if chunk_failures == 1 or chunk_failures % 20 == 0:
                    logger.warning(
                        "Warehouse live map ESDF chunk read failed flight_id=%s topic=%s "
                        "(nvblox_ok=%s failures=%s)",
                        flight_id,
                        esdf_topic,
                        nvblox_ok,
                        chunk_failures,
                    )

        if pose is not None or changed_chunks:
            health = WarehouseLiveHealthFlags(
                nvblox_ready=nvblox_ok,
                mapping_recording=True,
                stack_running=True,
                missing_mesh=False,
                missing_point_cloud=not bool(changed_chunks),
            )

            payload: dict[str, Any] = {
                "flight_id": flight_id,
                "timestamp": datetime.now(UTC),
                "health": health.model_dump(mode="python"),
                "changed_chunks": changed_chunks,
            }

            if pose is not None:
                pose_payload = pose.model_dump(mode="python")
                payload["pose"] = pose_payload
                payload["scan_path_sample"] = [pose_payload]
            else:
                payload["scan_path_sample"] = []

            update = normalize_live_map_payload(payload)
            await warehouse_live_map_stream.publish(update)

        try:
            await asyncio.wait_for(stop.wait(), timeout=max(0.2, poll_s))
        except TimeoutError:
            continue

    logger.info("Warehouse live map bridge stopped flight_id=%s", flight_id)


async def start_warehouse_live_map_bridge(flight_id: str) -> None:
    """Stream warehouse odometry + Nvblox ESDF pointcloud metadata into live voxel map."""
    if not env_truthy(settings.warehouse_live_map_publish):
        return

    global _bridge_task, _bridge_flight_id, _bridge_stop

    await stop_warehouse_live_map_bridge()

    stop = asyncio.Event()
    _bridge_stop = stop
    _bridge_flight_id = flight_id
    _bridge_task = asyncio.create_task(_publish_loop(flight_id, stop))


async def stop_warehouse_live_map_bridge() -> None:
    global _bridge_task, _bridge_flight_id, _bridge_stop

    if _bridge_stop is not None:
        _bridge_stop.set()

    if _bridge_task is not None:
        try:
            await asyncio.wait_for(_bridge_task, timeout=3.0)
        except TimeoutError:
            _bridge_task.cancel()
            try:
                await _bridge_task
            except asyncio.CancelledError:
                pass

    _bridge_task = None
    _bridge_flight_id = None
    _bridge_stop = None

    try:
        from backend.modules.warehouse.service.raw_pointcloud_live_map_bridge import (
            stop_raw_pointcloud_live_map_bridge,
        )

        await stop_raw_pointcloud_live_map_bridge()
    except Exception:
        logger.exception("Failed to stop raw point-cloud live map bridge")


def live_map_bridge_status() -> dict[str, Any]:
    running = _bridge_task is not None and not _bridge_task.done()
    return {
        "running": running,
        "flight_id": _bridge_flight_id,
    }