from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from .config import topic_env, topic_registry

logger = logging.getLogger(__name__)

_PUBLISHER_COUNT_RE = re.compile(r"Publisher count:\s*(\d+)")
_PUBLISHER_ENDPOINT_RE = re.compile(r"Endpoint type:\s*PUBLISHER")
_HZ_RE = re.compile(r"average rate:\s*([0-9.]+)")
_TOPIC_TYPE_RE = re.compile(r"Type:\s*(\S+)")

def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str, default: str) -> set[str]:
    raw = os.getenv(name, default)
    return {item.strip() for item in raw.split(",") if item.strip()}


@dataclass(frozen=True)
class TopicDiagnostic:
    key: str
    expected: str
    matched: str | None
    listed: bool
    publisher_count: int
    publishing: bool
    hz: float | None
    last_message_age_s: float | None
    healthy: bool
    message_type: str | None = None
    error: str | None = None
    readiness_state: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "expected": self.expected,
            "matched": self.matched,
            "listed": self.listed,
            "publisher_count": self.publisher_count,
            "publishing": self.publishing,
            "hz": self.hz,
            "last_message_age_s": self.last_message_age_s,
            "message_type": self.message_type,
            "healthy": self.healthy,
            "error": self.error,
            "readiness_state": self.readiness_state,
        }


@dataclass(frozen=True)
class TfChainDiagnostic:
    odom_frame: str
    base_link_frame: str
    camera_frame: str
    odom_to_base_link: bool
    base_link_to_camera: bool
    chain_ok: bool
    detail: str
    required_tf_edges: tuple[tuple[str, str], ...] = ()
    missing_tf_edges: tuple[tuple[str, str], ...] = ()
    sim_clock_ready: bool = True
    validation_source: str = "tf2_echo"

    def to_dict(self) -> dict[str, Any]:
        return {
            "odom_frame": self.odom_frame,
            "base_link_frame": self.base_link_frame,
            "camera_frame": self.camera_frame,
            "odom_to_base_link": self.odom_to_base_link,
            "base_link_to_camera": self.base_link_to_camera,
            "chain_ok": self.chain_ok,
            "detail": self.detail,
            "tf_available": self.chain_ok,
            "required_tf_edges": [list(edge) for edge in self.required_tf_edges],
            "missing_tf_edges": [list(edge) for edge in self.missing_tf_edges],
            "sim_clock_ready": self.sim_clock_ready,
            "validation_source": self.validation_source,
        }


def _ros_shell_prefix() -> str:
    ros_distro = os.getenv("ROS_DISTRO", "jazzy")
    ros_domain_id = os.getenv("ROS_DOMAIN_ID", "0")
    ros_ws_setup = os.getenv("ROS_WS_SETUP", "").strip()
    source_ws = f'source "{ros_ws_setup}" && ' if ros_ws_setup else ""
    sim_time = "export ROS_USE_SIM_TIME=1 && " if _use_sim_time_enabled() else ""
    return (
        f"source /opt/ros/{ros_distro}/setup.bash && "
        f"{source_ws}"
        f"export ROS_DOMAIN_ID={ros_domain_id} && "
        f"{sim_time}"
    )


def _ros_sim_time_args() -> str:
    return " --ros-args -p use_sim_time:=true" if _use_sim_time_enabled() else ""


def _run_ros_cmd(command: str, *, timeout_s: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", f"{_ros_shell_prefix()}{command}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )

def _topic_info(topic: str) -> tuple[int, str | None]:
    timeout_s = max(1.0, float(os.getenv("WAREHOUSE_TOPIC_INFO_TIMEOUT_S", "8.0")))
    try:
        result = _run_ros_cmd(
            f"ros2 topic info -v {shlex.quote(topic)} --no-daemon",
            timeout_s=timeout_s,
        )
    except (subprocess.TimeoutExpired, OSError):
        return 0, None

    output = f"{result.stdout}\n{result.stderr}"
    if "Unknown topic" in output:
        return 0, None

    pub_match = _PUBLISHER_COUNT_RE.search(output)
    type_match = _TOPIC_TYPE_RE.search(output)

    publishers = int(pub_match.group(1)) if pub_match else 0
    if publishers <= 0:
        publishers = len(_PUBLISHER_ENDPOINT_RE.findall(output))

    message_type = type_match.group(1) if type_match else None
    return publishers, message_type


def _publisher_count(topic: str) -> int:
    publishers, _ = _topic_info(topic)
    return publishers


def _topic_hz(topic: str) -> float | None:
    window = max(1, int(os.getenv("WAREHOUSE_TOPIC_HZ_WINDOW", "2")))
    timeout_s = max(2.0, float(os.getenv("WAREHOUSE_TOPIC_HZ_TIMEOUT_S", "5.0")))

    try:
        result = _run_ros_cmd(
            f"timeout {timeout_s} ros2 topic hz {shlex.quote(topic)} --window {window}"
            f" --no-daemon{_ros_sim_time_args()}",
            timeout_s=timeout_s + 1.0,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    match = _HZ_RE.search(result.stdout)
    return float(match.group(1)) if match else None


def _message_age_from_echo(topic: str, *, timeout_s: float) -> tuple[bool, float | None]:
    # This is intentionally opt-in. `ros2 topic echo --once` is expensive for
    # Image, PointCloud2, depth, and map topics, and it was making /health slow.
    if not _bool_env("WAREHOUSE_TOPIC_ECHO_PROBE", False):
        return False, None

    timeout_s = max(0.5, float(os.getenv("WAREHOUSE_TOPIC_ECHO_TIMEOUT_S", str(timeout_s))))

    try:
        result = _run_ros_cmd(
            f"timeout {timeout_s} ros2 topic echo {shlex.quote(topic)} --once --no-daemon",
            timeout_s=timeout_s + 0.75,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False, None

    output = result.stdout
    if not output.strip():
        return False, None

    sec_match = re.search(r"sec:\s*(\d+)", output)
    nsec_match = re.search(r"nanosec:\s*(\d+)", output)

    if sec_match and nsec_match:
        stamp = float(sec_match.group(1)) + float(nsec_match.group(1)) / 1_000_000_000.0
        wall_age = time.time() - stamp

        # Simulation stamps are often not wall-clock comparable.
        if wall_age < 0 or wall_age > 3600:
            return True, None

        return True, max(0.0, wall_age)

    if "timestamp_utc" in output:
        return True, 0.0

    return True, None


def _resolve_topic(
        key: str,
        primary: str,
        listed_topics: set[str] | None,
) -> str | None:
    candidates: list[str] = []

    if primary:
        candidates.append(primary)

    candidates.extend(topic_registry().aliases.get(key, []))

    seen: set[str] = set()
    ordered = [item for item in candidates if item and not (item in seen or seen.add(item))]

    # Fast path: trust the ROS graph list.
    if listed_topics is not None:
        for candidate in ordered:
            if candidate in listed_topics:
                return candidate

        # Do not fall back to hz/echo by default. Those subprocesses are slow.
        if not _bool_env("WAREHOUSE_TOPIC_RESOLVE_WITH_PROBES", False):
            return None

    # Cheap fallback: publisher count only.
    for candidate in ordered:
        if _publisher_count(candidate) > 0:
            return candidate

    # Expensive fallback only when explicitly enabled.
    if _bool_env("WAREHOUSE_TOPIC_RESOLVE_WITH_PROBES", False):
        for candidate in ordered:
            if _topic_hz(candidate) is not None:
                return candidate

            publishing, _ = _message_age_from_echo(candidate, timeout_s=1.0)
            if publishing:
                return candidate

    return None


def _probe_single_topic(
        key: str,
        primary: str,
        listed_topics: set[str] | None,
        *,
        max_age_s: float,
        min_hz: float,
) -> TopicDiagnostic:
    matched = _resolve_topic(key, primary, listed_topics)
    expected = primary

    if not matched:
        return TopicDiagnostic(
            key=key,
            expected=expected,
            matched=None,
            listed=False,
            publisher_count=0,
            publishing=False,
            hz=None,
            last_message_age_s=None,
            message_type=None,
            healthy=False,
            error="no matching topic in graph",
            readiness_state="topic_missing",
        )

    listed = bool(listed_topics and matched in listed_topics)
    publishers, message_type = _topic_info(matched)

    hz_keys = _csv_env(
        "WAREHOUSE_TOPIC_HZ_KEYS",
        "rgb_image,depth,raw_lidar,visual_slam_odom,local_odometry,imu",
    )
    require_hz = _bool_env("WAREHOUSE_TOPIC_REQUIRE_HZ", False)

    hz = _topic_hz(matched) if key in hz_keys else None

    echo_publishing = False
    age_s: float | None = None
    if _bool_env("WAREHOUSE_TOPIC_ECHO_PROBE", False):
        echo_publishing, age_s = _message_age_from_echo(matched, timeout_s=1.0)

    message_required_keys = _csv_env(
        "WAREHOUSE_TOPIC_REQUIRE_MESSAGES_KEYS",
        "rgb_image,depth,imu,visual_slam_odom,raw_lidar",
    )
    # Sensor streams must show actual messages (hz/echo), not just a bridge publisher
    # while Gazebo is paused or not yet running (gz sim without -r).
    if key in message_required_keys:
        publishing = bool(hz is not None or echo_publishing)
        # Gazebo contract relays can be slow to answer `ros2 topic hz`; trust publishers
        # when the graph lists the topic and gz-side sensors are live.
        if not publishing and topic_registry().profile == "gazebo" and _gazebo_sensor_stream_live(key):
            if publishers > 0 or listed:
                publishing = True
    else:
        publishing = bool(hz is not None or publishers > 0 or echo_publishing)

    age_ok = _message_age_is_fresh(age_s, max_age_s)
    hz_ok = True
    if hz is not None:
        hz_ok = hz >= min_hz
    elif require_hz and key in hz_keys:
        hz_ok = False

    healthy = bool(publishing and age_ok and hz_ok)

    error = None
    if not publishing:
        error = "no publishers/messages detected"
    elif not age_ok:
        error = f"stale (age {age_s:.2f}s > {max_age_s:.2f}s)"
    elif not hz_ok and hz is None:
        error = "rate unavailable"
    elif not hz_ok:
        error = f"rate too low ({hz} Hz < {min_hz} Hz)"

    return TopicDiagnostic(
        key=key,
        expected=expected,
        matched=matched,
        listed=listed,
        publisher_count=publishers,
        publishing=publishing,
        hz=hz,
        last_message_age_s=age_s,
        message_type=message_type,
        healthy=healthy,
        error=error,
        readiness_state=_readiness_state(
            matched=matched,
            listed=listed,
            publishers=publishers,
            publishing=publishing,
            healthy=healthy,
        ),
    )


def probe_topics(
        listed_topics: set[str] | None,
        *,
        keys: list[str] | None = None,
) -> dict[str, TopicDiagnostic]:
    topics = topic_env()
    max_age_s = float(os.getenv("WAREHOUSE_TOPIC_MAX_AGE_S", "3.0"))
    min_hz = float(os.getenv("WAREHOUSE_TOPIC_MIN_HZ", "0.5"))
    target_keys = keys or list(topics.keys())

    results: dict[str, TopicDiagnostic] = {}

    max_workers = max(1, min(8, int(os.getenv("WAREHOUSE_TOPIC_PROBE_WORKERS", "4"))))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _probe_single_topic,
                key,
                topics.get(key, ""),
                listed_topics,
                max_age_s=max_age_s,
                min_hz=min_hz if key not in {"local_odometry"} else 0.0,
            ): key
            for key in target_keys
            if topics.get(key)
        }

        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                results[key] = TopicDiagnostic(
                    key=key,
                    expected=topics.get(key, ""),
                    matched=None,
                    listed=False,
                    publisher_count=0,
                    publishing=False,
                    hz=None,
                    last_message_age_s=None,
                    message_type=None,
                    healthy=False,
                    error=str(exc),
                    readiness_state="probe_error",
                )

    return results

def _message_age_is_fresh(age_s: float | None, max_age_s: float) -> bool:
    if age_s is None:
        return True
    return age_s <= max_age_s



def _readiness_state(
    *,
    matched: str | None,
    listed: bool,
    publishers: int,
    publishing: bool,
    healthy: bool,
) -> str:
    if not matched:
        return "topic_missing"
    if not publishing:
        return "no_messages"
    if not healthy:
        return "unhealthy"
    if publishers <= 0:
        return "ok_via_messages"
    return "ok"



def _frame_candidates(frame_key: str, primary: str) -> list[str]:
    registry = topic_registry()
    aliases = registry.frame_aliases.get(frame_key, [])
    candidates = [primary, *aliases]
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        normalized = candidate.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def _use_sim_time_enabled() -> bool:
    return _bool_env("WAREHOUSE_USE_SIM_TIME", False) or _bool_env("WAREHOUSE_GAZEBO_SIM", False)


def _sim_clock_publishing() -> bool:
    if not _use_sim_time_enabled():
        return True
    timeout_s = max(1.0, float(os.getenv("WAREHOUSE_SIM_CLOCK_PROBE_TIMEOUT_S", "3.0")))
    try:
        result = _run_ros_cmd(
            f"timeout {timeout_s} ros2 topic echo /clock --once --no-daemon",
            timeout_s=timeout_s + 1.0,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    output = f"{result.stdout}\n{result.stderr}".strip()
    return bool(output) and "sec:" in output


def _parse_odometry_frames_from_echo(output: str) -> tuple[str | None, str | None]:
    parent_match = re.search(r"frame_id:\s*(\S+)", output)
    child_match = re.search(r"child_frame_id:\s*(\S+)", output)
    parent = parent_match.group(1) if parent_match else None
    child = child_match.group(1) if child_match else None
    return parent, child


def _gazebo_odom_declares_tf_edge(odom_frame: str, base_candidates: list[str]) -> tuple[bool, str | None]:
    registry = topic_registry()
    topics_to_try: list[str] = []
    contract_odom = topic_env().get("visual_slam_odom", "/warehouse/contract/odometry")
    if contract_odom:
        topics_to_try.append(str(contract_odom))
    if registry.profile == "gazebo":
        from .config import source_topic_env

        source_odom = source_topic_env("gazebo").get(
            "visual_slam_odom",
            "/warehouse/drone/odometry",
        )
        if source_odom and source_odom not in topics_to_try:
            topics_to_try.insert(0, str(source_odom))
    timeout_s = max(1.0, float(os.getenv("WAREHOUSE_TF_ODOM_FRAME_PROBE_TIMEOUT_S", "3.0")))
    for odom_topic in topics_to_try:
        try:
            result = _run_ros_cmd(
                f"timeout {timeout_s} ros2 topic echo {shlex.quote(odom_topic)} --once --no-daemon",
                timeout_s=timeout_s + 1.0,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        output = f"{result.stdout}\n{result.stderr}"
        parent, child = _parse_odometry_frames_from_echo(output)
        if not parent or not child:
            continue
        if parent.strip() != odom_frame:
            continue
        for candidate in base_candidates:
            if child.strip() == candidate:
                return True, candidate
    return False, None


def _static_tf_edge_ok(parent: str, child: str) -> bool:
    timeout_s = max(1.0, float(os.getenv("WAREHOUSE_TF_STATIC_PROBE_TIMEOUT_S", "3.0")))
    try:
        result = _run_ros_cmd(
            f"timeout {timeout_s} ros2 topic echo /tf_static --once --no-daemon",
            timeout_s=timeout_s + 1.0,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    output = f"{result.stdout}\n{result.stderr}"
    parent_pattern = re.compile(
        rf"frame_id:\s*{re.escape(parent)}[\s\S]*?child_frame_id:\s*{re.escape(child)}",
        re.MULTILINE,
    )
    return bool(parent_pattern.search(output))


def _tf_echo_ok(parent: str, child: str, *, timeout_s: float | None = None) -> bool:
    if timeout_s is None:
        timeout_s = float(os.getenv("WAREHOUSE_TF_PROBE_TIMEOUT_S", "8.0"))
    sim_args = _ros_sim_time_args()
    attempts = max(1, int(os.getenv("WAREHOUSE_TF_PROBE_ATTEMPTS", "2")))
    for attempt in range(attempts):
        try:
            result = _run_ros_cmd(
                f"timeout {timeout_s} ros2 run tf2_ros tf2_echo "
                f"{shlex.quote(parent)} {shlex.quote(child)}{sim_args}",
                timeout_s=timeout_s + 2.0,
            )
        except (subprocess.TimeoutExpired, OSError):
            if attempt + 1 < attempts:
                time.sleep(0.75)
            continue
        output = f"{result.stdout}\n{result.stderr}"
        if "At time" in output or "Translation:" in output:
            return True
        if "frame does not exist" in output.lower():
            if attempt + 1 < attempts:
                time.sleep(0.75)
            continue
        if result.returncode == 0 and bool(output.strip()):
            return True
        if attempt + 1 < attempts:
            time.sleep(0.75)
    return False


def probe_gazebo_publishing(gz_topic: str, *, timeout_s: float = 3.0) -> bool:
    if not shutil.which("gz"):
        return False
    partition = os.getenv("GZ_PARTITION", "").strip()
    env = os.environ.copy()
    if partition:
        env["GZ_PARTITION"] = partition
    try:
        result = subprocess.run(
            ["timeout", str(max(1.0, timeout_s)), "gz", "topic", "-t", gz_topic, "-f"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s + 1.0,
            env=env,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return bool(result.stdout.strip())


_GAZEBO_SENSOR_PROBE_CACHE: tuple[float, dict[str, Any]] | None = None


def _gazebo_sensor_snapshot() -> dict[str, Any]:
    global _GAZEBO_SENSOR_PROBE_CACHE
    ttl_s = max(0.5, float(os.getenv("WAREHOUSE_GAZEBO_PROBE_CACHE_S", "2.0")))
    now = time.monotonic()
    if _GAZEBO_SENSOR_PROBE_CACHE is not None:
        cached_at, cached = _GAZEBO_SENSOR_PROBE_CACHE
        if now - cached_at < ttl_s:
            return cached
    status = probe_gazebo_sensors()
    _GAZEBO_SENSOR_PROBE_CACHE = (now, status)
    return status


def _gazebo_imu_topic() -> str:
    return os.getenv(
        "WAREHOUSE_GAZEBO_IMU_TOPIC",
        "/world/iris_warehouse/model/iris_rplidar_rgbd/model/iris_with_standoffs/"
        "link/imu_link/sensor/imu_sensor/imu",
    ).strip()


def _gazebo_sensor_stream_live(key: str) -> bool:
    if topic_registry().profile != "gazebo":
        return False
    status = _gazebo_sensor_snapshot()
    field_by_key = {
        "rgb_image": "rgb_publishing",
        "depth": "depth_publishing",
        "visual_slam_odom": "odom_publishing",
        "raw_lidar": "rgb_publishing",
        "imu": "imu_publishing",
    }
    field = field_by_key.get(key)
    if field is None:
        return False
    return bool(status.get(field))


def probe_gazebo_sensors() -> dict[str, Any]:
    rgb_topic = os.getenv("WAREHOUSE_GAZEBO_RGB_TOPIC", "/warehouse/front/rgbd/image")
    depth_topic = os.getenv(
        "WAREHOUSE_GAZEBO_DEPTH_TOPIC",
        os.getenv("WAREHOUSE_DEPTH_TOPIC", "/warehouse/front/rgbd/depth_image"),
    )
    odom_topic = os.getenv("WAREHOUSE_GAZEBO_ODOM_TOPIC", "/warehouse/drone/odometry")
    imu_topic = _gazebo_imu_topic()
    timeout_s = float(os.getenv("WAREHOUSE_GAZEBO_PROBE_TIMEOUT_S", "3.0"))
    rgb = probe_gazebo_publishing(rgb_topic, timeout_s=timeout_s)
    depth = probe_gazebo_publishing(depth_topic, timeout_s=timeout_s)
    odom = probe_gazebo_publishing(odom_topic, timeout_s=timeout_s)
    imu = probe_gazebo_publishing(imu_topic, timeout_s=timeout_s)
    partition = os.getenv("GZ_PARTITION", "").strip() or None
    sim_publishing = bool(rgb and depth and odom)
    return {
        "partition": partition,
        "rgb_topic": rgb_topic,
        "depth_topic": depth_topic,
        "odom_topic": odom_topic,
        "imu_topic": imu_topic,
        "rgb_publishing": rgb,
        "depth_publishing": depth,
        "odom_publishing": odom,
        "imu_publishing": imu,
        "sim_publishing": sim_publishing,
        "start_hint": (
            "Start Gazebo running (gz sim -r world.sdf) or press Play, then verify with: "
            f"gz topic -e -t {rgb_topic}"
        ),
    }


def _resolve_tf_edge(
    parent_candidates: list[str],
    child_candidates: list[str],
) -> tuple[str, str] | None:
    for parent in parent_candidates:
        for child in child_candidates:
            if _tf_echo_ok(parent, child):
                return parent, child
    return None


def probe_tf_chain() -> TfChainDiagnostic:
    registry = topic_registry()
    frames = registry.frames
    odom = frames.get("odom", "odom")
    base_primary = frames.get("base_link", "base_link")
    camera_primary = frames.get("camera", "front_rgbd_camera_link")
    base_candidates = _frame_candidates("base_link", base_primary)
    camera_candidates = _frame_candidates("camera", camera_primary)
    sim_clock_ready = _sim_clock_publishing()
    validation_source = "tf2_echo"

    odom_base_edge = _resolve_tf_edge([odom], base_candidates)
    odom_base = odom_base_edge is not None
    resolved_base = odom_base_edge[1] if odom_base_edge else base_primary

    if not odom_base and registry.profile == "gazebo":
        declared, resolved_child = _gazebo_odom_declares_tf_edge(odom, base_candidates)
        if declared and resolved_child:
            odom_base = True
            resolved_base = resolved_child
            validation_source = "gazebo_odom_frames"

    base_camera_edge = (
        _resolve_tf_edge([resolved_base], camera_candidates) if odom_base else None
    )
    base_camera = base_camera_edge is not None
    resolved_camera = base_camera_edge[1] if base_camera_edge else camera_primary

    if odom_base and not base_camera:
        for camera in camera_candidates:
            if _static_tf_edge_ok(resolved_base, camera):
                base_camera = True
                resolved_camera = camera
                validation_source = (
                    f"{validation_source}+tf_static"
                    if validation_source != "tf2_echo"
                    else "tf_static"
                )
                break

    required_edges = ((odom, resolved_base), (resolved_base, resolved_camera))
    missing_edges: list[tuple[str, str]] = []
    if not odom_base:
        missing_edges.append((odom, resolved_base))
    if odom_base and not base_camera:
        missing_edges.append((resolved_base, resolved_camera))

    chain_ok = odom_base and base_camera
    if chain_ok:
        detail = "ok"
    elif not sim_clock_ready and registry.profile == "gazebo":
        detail = (
            "waiting for /clock (Gazebo sim time); press Play or start with gz sim -r <world>.sdf"
        )
    else:
        detail = "; ".join(f"{parent}->{child} missing" for parent, child in missing_edges)

    return TfChainDiagnostic(
        odom_frame=odom,
        base_link_frame=resolved_base,
        camera_frame=resolved_camera,
        odom_to_base_link=odom_base,
        base_link_to_camera=base_camera,
        chain_ok=chain_ok,
        detail=detail,
        required_tf_edges=tuple(required_edges),
        missing_tf_edges=tuple(missing_edges),
        sim_clock_ready=sim_clock_ready,
        validation_source=validation_source,
    )


def _coerce_topic_diagnostic(
    key: str,
    diag: TopicDiagnostic | dict[str, Any],
) -> TopicDiagnostic:
    if isinstance(diag, TopicDiagnostic):
        return diag
    if not isinstance(diag, dict):
        return TopicDiagnostic(
            key=key,
            expected="",
            matched=None,
            listed=False,
            publisher_count=0,
            publishing=False,
            hz=None,
            last_message_age_s=None,
            healthy=False,
        )
    return TopicDiagnostic(
        key=str(diag.get("key") or key),
        expected=str(diag.get("expected") or ""),
        matched=diag.get("matched") if isinstance(diag.get("matched"), str) else None,
        listed=bool(diag.get("listed")),
        publisher_count=int(diag.get("publisher_count") or 0),
        publishing=bool(diag.get("publishing")),
        hz=float(diag["hz"]) if diag.get("hz") is not None else None,
        last_message_age_s=(
            float(diag["last_message_age_s"])
            if diag.get("last_message_age_s") is not None
            else None
        ),
        healthy=bool(diag.get("healthy")),
        message_type=(
            diag.get("message_type")
            if isinstance(diag.get("message_type"), str)
            else None
        ),
        error=diag.get("error") if isinstance(diag.get("error"), str) else None,
        readiness_state=(
            diag.get("readiness_state")
            if isinstance(diag.get("readiness_state"), str)
            else None
        ),
    )


def summarize_diagnostics(
    diagnostics: dict[str, TopicDiagnostic | dict[str, Any]],
    *,
    include_nvblox: bool = True,
) -> dict[str, Any]:
    registry = topic_registry()
    normalized = {key: _coerce_topic_diagnostic(key, diag) for key, diag in diagnostics.items()}

    def _healthy_for_summary(key: str) -> bool:
        diag = normalized.get(key)
        if not diag:
            return False
        if diag.readiness_state in {"shallow_present", "ok_graph_presence"}:
            return True
        return bool(diag.healthy)

    missing_required = [
        key for key in registry.required_for_perception if not _healthy_for_summary(key)
    ]
    camera_ok = _healthy_for_summary("rgb_image") or (
        _healthy_for_summary("left_image") and _healthy_for_summary("right_image")
    )
    if camera_ok:
        missing_required = [key for key in missing_required if key != "rgb_image"]
    nvblox_any = any(_healthy_for_summary(key) for key in registry.required_for_nvblox_any)
    if include_nvblox:
        missing_nvblox = (
            [key for key in registry.required_for_nvblox_any if not _healthy_for_summary(key)]
            if not nvblox_any
            else []
        )
    else:
        missing_nvblox = []
    return {
        "missing_required_topics": missing_required,
        "missing_nvblox_topics": missing_nvblox,
        "topic_matches": {
            key: {
                "expected": diag.expected,
                "matched": diag.matched,
                "healthy": diag.healthy,
                "error": diag.error,
                "publisher_count": diag.publisher_count,
                "publishing": diag.publishing,
                "hz": diag.hz,
                "last_message_age_s": diag.last_message_age_s,
                "message_type": diag.message_type,
                "readiness_state": diag.readiness_state,
                "verify_cmd": (
                    f"timeout 5 ros2 topic hz {diag.matched or diag.expected}"
                    if diag.matched or diag.expected
                    else None
                ),
            }
            for key, diag in normalized.items()
        },
    }


# Keep the real subprocess-based probe available. The fast function below is the
# default because /health must not run ros2 topic hz/echo/info for every topic.
_probe_topics_deep = probe_topics


def _imu_topic_from_graph(listed_topics: set[str]) -> str | None:
    matches = [
        topic
        for topic in listed_topics
        if topic.startswith("/") and topic.endswith("/imu") and "imu" in topic.lower()
    ]
    if not matches:
        return None
    return sorted(matches, key=len)[0]


def _fast_resolve_topic_from_graph(
        key: str,
        primary: str,
        listed_topics: set[str] | None,
) -> str | None:
    if not listed_topics:
        return None

    candidates: list[str] = []
    if primary:
        candidates.append(primary)
    candidates.extend(topic_registry().aliases.get(key, []))

    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if normalized in listed_topics:
            return normalized

    if key == "imu":
        return _imu_topic_from_graph(listed_topics)

    return None


def _fast_graph_topic_diagnostic(
        key: str,
        primary: str,
        listed_topics: set[str] | None,
) -> TopicDiagnostic:
    matched = _fast_resolve_topic_from_graph(key, primary, listed_topics)
    healthy = matched is not None

    return TopicDiagnostic(
        key=key,
        expected=primary,
        matched=matched,
        listed=healthy,
        publisher_count=1 if healthy else 0,
        publishing=healthy,
        hz=None,
        last_message_age_s=None,
        message_type=None,
        healthy=healthy,
        error=None if healthy else "topic not listed in graph",
        readiness_state="ok_graph_presence" if healthy else "topic_missing",
    )


def _probe_topics_presence(
        listed_topics: set[str] | None,
        *,
        keys: list[str] | None = None,
) -> dict[str, TopicDiagnostic]:
    topics = topic_env()
    target_keys = keys or list(topics.keys())
    return {
        key: _fast_graph_topic_diagnostic(key, topics.get(key, ""), listed_topics)
        for key in target_keys
        if topics.get(key)
    }


def probe_topics(
        listed_topics: set[str] | None,
        *,
        keys: list[str] | None = None,
) -> dict[str, TopicDiagnostic]:
    mode = os.getenv("WAREHOUSE_TOPIC_HEALTH_MODE", "presence").strip().lower()
    if mode in {"deep", "strict", "hz", "publishers"}:
        return _probe_topics_deep(listed_topics, keys=keys)
    return _probe_topics_presence(listed_topics, keys=keys)
