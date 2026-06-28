from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import shlex
import struct
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

from backend.core.config.runtime import env_truthy, settings
from backend.infrastructure.warehouse.bridge_config import (
    bridge_config_path,
    list_ros2_topics,
    load_bridge_config,
    ros_command_env,
)
from backend.modules.warehouse.service.map_source_config import WAREHOUSE_LIVE_MAP_SOURCES
from backend.modules.warehouse.service.nvblox_status import nvblox_status_tracker
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
_bridge_lock = asyncio.Lock()


def _setting_str(name: str, default: str = "") -> str:
    return str(getattr(settings, name, default) or "").strip()


def _setting_float(name: str, default: float, *, minimum: float) -> float:
    try:
        return max(minimum, float(getattr(settings, name, default)))
    except (TypeError, ValueError):
        return max(minimum, default)


def _setting_int(name: str, default: int, *, minimum: int) -> int:
    try:
        return max(minimum, int(getattr(settings, name, default)))
    except (TypeError, ValueError):
        return max(minimum, default)


def _setting_bool(name: str, default: bool = False) -> bool:
    raw = getattr(settings, name, default)
    if isinstance(raw, str):
        return env_truthy(raw)
    return bool(raw)


def _ros2_workspace() -> Path:
    raw = _setting_str("warehouse_ros2_ws", "ros2_ws") or "ros2_ws"
    return Path(raw).expanduser().resolve()


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


def _esdf_topic() -> str:
    from backend.modules.warehouse.service.bridge_flow import resolve_warehouse_bridge_flow

    configured = _setting_str("warehouse_esdf_topic")
    if configured:
        return configured
    flow = resolve_warehouse_bridge_flow()
    return (
        "/nvblox_node/static_esdf_pointcloud" if flow.gazebo_sim else "/warehouse/contract/map/esdf"
    )


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


def _ros_setup_command(ws: Path) -> str:
    install_setup = ws / "install/setup.bash"
    return (
        "source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash && "
        f"source {shlex.quote(str(install_setup))}"
    )


def _run_ros2_command(
    *,
    ws: Path,
    ros_args: Iterable[str],
    shell_timeout_s: float,
    process_timeout_s: float,
) -> subprocess.CompletedProcess[str] | None:
    command = (
        f"{_ros_setup_command(ws)} && "
        f"timeout {shlex.quote(str(max(1, int(math.ceil(shell_timeout_s)))))} "
        f"ros2 {' '.join(shlex.quote(str(arg)) for arg in ros_args)}"
    )
    try:
        return subprocess.run(
            ["bash", "-lc", command],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=process_timeout_s,
            check=False,
            env=ros_command_env(),
        )
    except subprocess.TimeoutExpired:
        logger.debug("ROS command timed out: ros2 %s", " ".join(map(str, ros_args)))
        return None
    except OSError:
        logger.debug(
            "ROS command failed to start: ros2 %s", " ".join(map(str, ros_args)), exc_info=True
        )
        return None


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


def _list_ros2_topics_safe(ws: Path) -> set[str]:
    try:
        return set(list_ros2_topics(ws))
    except RuntimeError:
        logger.debug("Could not list ROS2 topics", exc_info=True)
        return set()


def _nvblox_ready_from_topics(*, topics: set[str], esdf_topic: str) -> bool:
    status = nvblox_status_tracker.status()
    if status in {"live", "degraded", "warming"}:
        return status == "live"

    nvblox_status_tracker.note_topic_list(topics)
    if esdf_topic in topics:
        return True
    return any(str(topic).startswith("/nvblox_node/") for topic in topics)


def _nvblox_ready(*, ws: Path, esdf_topic: str) -> bool:
    return _nvblox_ready_from_topics(topics=_list_ros2_topics_safe(ws), esdf_topic=esdf_topic)


def _read_pointcloud2_yaml(*, topic: str, ws: Path) -> dict[str, Any] | None:
    """
    Development bridge: reads one PointCloud2 sample via ROS CLI and parses YAML.

    This is expensive for large PointCloud2 messages. Prefer the persistent rclpy
    subscribers used by the raw/colored/nvblox live-map bridges for production.
    """
    result = _run_ros2_command(
        ws=ws,
        ros_args=("topic", "echo", topic, "--once", "--full-length"),
        shell_timeout_s=2.0,
        process_timeout_s=4.0,
    )
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return None

    try:
        payload = next(
            (doc for doc in yaml.safe_load_all(result.stdout) if isinstance(doc, dict)),
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


def _field_spec(
    field: dict[str, Any],
    *,
    point_step: int,
) -> tuple[int, int] | None:
    try:
        offset = int(field["offset"])
        datatype = int(field["datatype"])
    except (KeyError, TypeError, ValueError):
        return None

    size = _POINTFIELD_DATATYPE_SIZE.get(datatype)
    if size is None or offset < 0 or offset + size > point_step:
        return None
    return offset, datatype


def _pointcloud2_to_chunk(
    payload: dict[str, Any],
    *,
    flight_id: str,
    sequence: int,
    max_points: int,
    source_topic: str = "/nvblox_node/static_esdf_pointcloud",
) -> dict[str, Any] | None:
    del flight_id
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

    if not all(name in field_by_name for name in ("x", "y", "z")):
        return None

    try:
        raw = bytes(int(value) & 0xFF for value in data)
    except (TypeError, ValueError):
        return None

    total_points = len(raw) // point_step
    if total_points <= 0:
        return None

    max_preview_points = max(1, int(max_points))
    stride = max(1, math.ceil(total_points / max_preview_points))
    little_endian = not is_bigendian

    x_spec = _field_spec(field_by_name["x"], point_step=point_step)
    y_spec = _field_spec(field_by_name["y"], point_step=point_step)
    z_spec = _field_spec(field_by_name["z"], point_step=point_step)
    if x_spec is None or y_spec is None or z_spec is None:
        return None

    x_offset, x_type = x_spec
    y_offset, y_type = y_spec
    z_offset, z_type = z_spec

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

        if len(sampled) >= max_preview_points:
            break

    if not sampled:
        return None

    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    frame_id = str(header.get("frame_id") or "").strip()
    if not frame_id:
        return None
    chunk_payload = {
        "format": "xyz_preview_v1",
        "frame_id": frame_id,
        "source_topic": source_topic,
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
        "source": "nvblox_esdf",
        "layer": "esdf",
        "source_topic": source_topic,
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

    max_points = _setting_int("warehouse_live_map_max_preview_points", 500, minimum=100)
    return _pointcloud2_to_chunk(
        payload,
        flight_id=flight_id,
        sequence=sequence,
        max_points=max_points,
        source_topic=topic,
    )


async def _publish_loop(flight_id: str, stop: asyncio.Event) -> None:
    ws = _ros2_workspace()
    odom_topic = _odometry_topic()
    esdf_topic = _esdf_topic()
    poll_s = _setting_float("warehouse_live_map_poll_s", 1.0, minimum=0.2)
    cli_pointcloud_enabled = _setting_bool("warehouse_live_map_cli_pointcloud_enabled", False)
    cli_pointcloud_poll_s = _setting_float(
        "warehouse_live_map_cli_pointcloud_poll_s",
        max(2.0, poll_s * 5.0),
        minimum=1.0,
    )
    next_chunk_at = 0.0
    chunk_sequence = 0

    logger.info(
        "Warehouse live map bridge started flight_id=%s odom=%s esdf=%s config=%s cli_pointcloud=%s",
        flight_id,
        odom_topic,
        esdf_topic,
        bridge_config_path(ws),
        cli_pointcloud_enabled,
    )

    try:
        while not stop.is_set():
            try:
                pose_result, topics_result = await asyncio.gather(
                    asyncio.to_thread(_read_odometry_pose, topic=odom_topic, ws=ws),
                    asyncio.to_thread(_list_ros2_topics_safe, ws),
                )
                pose = pose_result if isinstance(pose_result, WarehouseLivePose) else None
                topics = topics_result if isinstance(topics_result, set) else set()
                nvblox_ok = _nvblox_ready_from_topics(topics=topics, esdf_topic=esdf_topic)
                nvblox_status = nvblox_status_tracker.status()

                rgbd_topic = WAREHOUSE_LIVE_MAP_SOURCES["rgbd_colored"].topic
                lidar_topic = WAREHOUSE_LIVE_MAP_SOURCES["mid360_raw"].topic
                changed_chunks: list[dict[str, Any]] = []

                now = time.monotonic()
                if cli_pointcloud_enabled and nvblox_ok and now >= next_chunk_at:
                    next_chunk_at = now + cli_pointcloud_poll_s
                    chunk_sequence += 1
                    chunk = await asyncio.to_thread(
                        _read_nvblox_chunk,
                        flight_id=flight_id,
                        topic=esdf_topic,
                        ws=ws,
                        sequence=chunk_sequence,
                    )
                    if chunk is not None:
                        changed_chunks.append(chunk)

                if pose is not None or changed_chunks:
                    health = WarehouseLiveHealthFlags(
                        nvblox_ready=nvblox_ok or nvblox_status == "live",
                        nvblox_status=nvblox_status,
                        rgbd_live=rgbd_topic in topics,
                        lidar_live=lidar_topic in topics,
                        mapping_recording=True,
                        stack_running=bool(topics),
                        missing_mesh=nvblox_status not in {"live", "degraded", "warming"},
                        missing_point_cloud=not (nvblox_ok or changed_chunks),
                    )

                    pose_payload = pose.model_dump(mode="python") if pose is not None else None
                    payload: dict[str, Any] = {
                        "flight_id": flight_id,
                        "timestamp": datetime.now(UTC),
                        "health": health.model_dump(mode="python"),
                        "changed_chunks": changed_chunks,
                    }
                    frames = {
                        str(chunk.get("frame_id") or "").strip()
                        for chunk in changed_chunks
                        if isinstance(chunk, dict)
                    }
                    if pose is not None:
                        frames.add(pose.frame_id)
                    frames.discard("")
                    if len(frames) != 1:
                        raise ValueError(
                            f"Live-map bridge produced missing or mixed frames: {sorted(frames)}"
                        )
                    payload["frame_id"] = frames.pop()
                    if pose_payload is not None:
                        payload["pose"] = pose_payload
                        payload["scan_path_sample"] = [pose_payload]

                    update = normalize_live_map_payload(payload)
                    await warehouse_live_map_stream.publish(update)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Warehouse live map bridge publish iteration failed")

            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_s)
            except TimeoutError:
                continue
    finally:
        logger.info("Warehouse live map bridge stopped flight_id=%s", flight_id)


async def start_warehouse_live_map_bridge(flight_id: str) -> None:
    """Stream warehouse odometry + Nvblox ESDF pointcloud metadata into live voxel map."""
    if not env_truthy(settings.warehouse_live_map_publish):
        return

    global _bridge_task, _bridge_flight_id, _bridge_stop

    async with _bridge_lock:
        await _stop_warehouse_live_map_bridge_locked(stop_child_bridges=False)
        stop = asyncio.Event()
        _bridge_stop = stop
        _bridge_flight_id = flight_id
        _bridge_task = asyncio.create_task(
            _publish_loop(flight_id, stop),
            name=f"warehouse-live-map-bridge:{flight_id}",
        )


async def _stop_child_bridges() -> None:
    child_stoppers = (
        (
            "raw point-cloud live map bridge",
            "backend.modules.warehouse.service.raw_pointcloud_live_map_bridge",
            "stop_raw_pointcloud_live_map_bridge",
        ),
        (
            "colored point-cloud live map bridge",
            "backend.modules.warehouse.service.colored_pointcloud_live_map_bridge",
            "stop_colored_pointcloud_live_map_bridge",
        ),
        (
            "nvblox layers live map bridge",
            "backend.modules.warehouse.service.nvblox_layers_live_map_bridge",
            "stop_nvblox_layers_live_map_bridge",
        ),
    )

    for label, module_name, function_name in child_stoppers:
        try:
            module = __import__(module_name, fromlist=[function_name])
            stopper = getattr(module, function_name)
            await stopper()
        except Exception:
            logger.exception("Failed to stop %s", label)


async def _stop_warehouse_live_map_bridge_locked(*, stop_child_bridges: bool = True) -> None:
    global _bridge_task, _bridge_flight_id, _bridge_stop

    task = _bridge_task
    stop = _bridge_stop
    if stop is not None:
        stop.set()

    if task is not None:
        try:
            await asyncio.wait_for(task, timeout=3.0)
        except TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Warehouse live map bridge task stopped with an error")

    _bridge_task = None
    _bridge_flight_id = None
    _bridge_stop = None

    if stop_child_bridges:
        await _stop_child_bridges()


async def stop_warehouse_live_map_bridge() -> None:
    async with _bridge_lock:
        await _stop_warehouse_live_map_bridge_locked(stop_child_bridges=True)


def live_map_bridge_status() -> dict[str, Any]:
    running = _bridge_task is not None and not _bridge_task.done()
    return {
        "running": running,
        "flight_id": _bridge_flight_id,
    }
