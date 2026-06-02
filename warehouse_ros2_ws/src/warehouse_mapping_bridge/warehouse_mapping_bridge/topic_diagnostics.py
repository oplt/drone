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

    def to_dict(self) -> dict[str, Any]:
        return {
            "odom_frame": self.odom_frame,
            "base_link_frame": self.base_link_frame,
            "camera_frame": self.camera_frame,
            "odom_to_base_link": self.odom_to_base_link,
            "base_link_to_camera": self.base_link_to_camera,
            "chain_ok": self.chain_ok,
            "detail": self.detail,
        }


def _ros_shell_prefix() -> str:
    ros_distro = os.getenv("ROS_DISTRO", "jazzy")
    ros_domain_id = os.getenv("ROS_DOMAIN_ID", "0")
    ros_ws_setup = os.getenv("ROS_WS_SETUP", "").strip()
    source_ws = f'source "{ros_ws_setup}" && ' if ros_ws_setup else ""
    return (
        f"source /opt/ros/{ros_distro}/setup.bash && "
        f"{source_ws}"
        f"export ROS_DOMAIN_ID={ros_domain_id} && "
    )


def _run_ros_cmd(command: str, *, timeout_s: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", f"{_ros_shell_prefix()}{command}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )

def _topic_info(topic: str) -> tuple[int, str | None]:
    timeout_s = max(0.5, float(os.getenv("WAREHOUSE_TOPIC_INFO_TIMEOUT_S", "1.5")))
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
    timeout_s = max(0.75, float(os.getenv("WAREHOUSE_TOPIC_HZ_TIMEOUT_S", "2.0")))

    try:
        result = _run_ros_cmd(
            f"timeout {timeout_s} ros2 topic hz {shlex.quote(topic)} --window {window} --no-daemon",
            timeout_s=timeout_s + 0.75,
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


def _tf_echo_ok(parent: str, child: str, *, timeout_s: float = 2.0) -> bool:
    try:
        result = _run_ros_cmd(
            f"timeout {timeout_s} ros2 run tf2_ros tf2_echo "
            f"{shlex.quote(parent)} {shlex.quote(child)}",
            timeout_s=timeout_s + 1.0,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    output = f"{result.stdout}\n{result.stderr}"
    return "At time" in output or "Translation:" in output


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


def probe_gazebo_sensors() -> dict[str, Any]:
    rgb_topic = os.getenv("WAREHOUSE_GAZEBO_RGB_TOPIC", "/warehouse/front/rgbd/image")
    depth_topic = os.getenv(
        "WAREHOUSE_GAZEBO_DEPTH_TOPIC",
        os.getenv("WAREHOUSE_DEPTH_TOPIC", "/warehouse/front/rgbd/depth_image"),
    )
    odom_topic = os.getenv("WAREHOUSE_GAZEBO_ODOM_TOPIC", "/warehouse/drone/odometry")
    timeout_s = float(os.getenv("WAREHOUSE_GAZEBO_PROBE_TIMEOUT_S", "3.0"))
    rgb = probe_gazebo_publishing(rgb_topic, timeout_s=timeout_s)
    depth = probe_gazebo_publishing(depth_topic, timeout_s=timeout_s)
    odom = probe_gazebo_publishing(odom_topic, timeout_s=timeout_s)
    partition = os.getenv("GZ_PARTITION", "").strip() or None
    sim_publishing = bool(rgb and depth and odom)
    return {
        "partition": partition,
        "rgb_topic": rgb_topic,
        "depth_topic": depth_topic,
        "odom_topic": odom_topic,
        "rgb_publishing": rgb,
        "depth_publishing": depth,
        "odom_publishing": odom,
        "sim_publishing": sim_publishing,
        "start_hint": (
            "Start Gazebo running (gz sim -r world.sdf) or press Play, then verify with: "
            f"gz topic -e -t {rgb_topic}"
        ),
    }


def probe_tf_chain() -> TfChainDiagnostic:
    frames = topic_registry().frames
    odom = frames.get("odom", "odom")
    base_candidates = _frame_candidates("base_link", frames.get("base_link", "base_link"))
    camera_candidates = _frame_candidates("camera", frames.get("camera", "front_rgbd_camera_link"))

    matched_base = next((frame for frame in base_candidates if _tf_echo_ok(odom, frame)), None)
    odom_base = matched_base is not None

    matched_camera = None
    base_camera = False
    if matched_base is not None:
        matched_camera = next(
            (frame for frame in camera_candidates if _tf_echo_ok(matched_base, frame)),
            None,
        )
        base_camera = matched_camera is not None

    chain_ok = odom_base and base_camera
    parts: list[str] = []
    if not odom_base:
        parts.append(f"{odom}->[{','.join(base_candidates)}] missing")
    if matched_base and not base_camera:
        parts.append(f"{matched_base}->[{','.join(camera_candidates)}] missing")
    detail = "ok" if chain_ok else "; ".join(parts)
    return TfChainDiagnostic(
        odom_frame=odom,
        base_link_frame=matched_base or base_candidates[0],
        camera_frame=matched_camera or camera_candidates[0],
        odom_to_base_link=odom_base,
        base_link_to_camera=base_camera,
        chain_ok=chain_ok,
        detail=detail,
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
        message_type=diag.get("message_type") if isinstance(diag.get("message_type"), str) else None,
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

    missing_required = [key for key in registry.required_for_perception if not _healthy_for_summary(key)]
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