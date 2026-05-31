from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from time import monotonic
from typing import Any

from .config import topic_env, topic_registry

logger = logging.getLogger(__name__)

_PUBLISHER_COUNT_RE = re.compile(r"Publisher count:\s*(\d+)")
_HZ_RE = re.compile(r"average rate:\s*([0-9.]+)")
_TOPIC_TYPE_RE = re.compile(r"Type:\s*(\S+)")


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
    try:
        result = _run_ros_cmd(f"ros2 topic info {shlex.quote(topic)} --no-daemon", timeout_s=4.0)
    except (subprocess.TimeoutExpired, OSError):
        return 0, None
    output = f"{result.stdout}\n{result.stderr}"
    if "Unknown topic" in output:
        return 0, None
    pub_match = _PUBLISHER_COUNT_RE.search(output)
    type_match = _TOPIC_TYPE_RE.search(output)
    publishers = int(pub_match.group(1)) if pub_match else 0
    message_type = type_match.group(1) if type_match else None
    return publishers, message_type


def _publisher_count(topic: str) -> int:
    publishers, _ = _topic_info(topic)
    return publishers


def _topic_hz(topic: str) -> float | None:
    window = max(1, int(os.getenv("WAREHOUSE_TOPIC_HZ_WINDOW", "3")))
    timeout_s = max(1.5, float(os.getenv("WAREHOUSE_TOPIC_HZ_TIMEOUT_S", "2.5")))
    try:
        result = _run_ros_cmd(
            f"timeout {timeout_s} ros2 topic hz {shlex.quote(topic)} --window {window} --no-daemon",
            timeout_s=timeout_s + 1.0,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    match = _HZ_RE.search(result.stdout)
    return float(match.group(1)) if match else None


def _message_age_from_echo(topic: str, *, timeout_s: float) -> tuple[bool, float | None]:
    import time

    try:
        result = _run_ros_cmd(
            f"timeout {timeout_s} ros2 topic echo {shlex.quote(topic)} --once --no-daemon",
            timeout_s=timeout_s + 0.5,
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
        return True, max(0.0, time.time() - stamp)
    if "timestamp_utc" in output:
        return True, 0.0
    return True, None


def _resolve_topic(
    key: str,
    primary: str,
    listed_topics: set[str] | None,
) -> str | None:
    if primary and listed_topics and primary in listed_topics:
        return primary
    for alias in topic_registry().aliases.get(key, []):
        if listed_topics and alias in listed_topics:
            return alias
    if primary and _publisher_count(primary) > 0:
        return primary
    for alias in topic_registry().aliases.get(key, []):
        if _publisher_count(alias) > 0:
            return alias
    return None


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
    if publishers <= 0:
        return "no_publisher"
    if not publishing:
        return "no_messages"
    if not healthy:
        return "unhealthy"
    return "ok"


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
    publishing, age_s = _message_age_from_echo(matched, timeout_s=2.0)
    hz = _topic_hz(matched) if publishing else None
    age_ok = age_s is None or age_s <= max_age_s
    hz_ok = hz is None or hz >= min_hz
    healthy = publishers > 0 and publishing and age_ok and hz_ok
    error = None
    if publishers <= 0:
        error = "no publishers"
    elif not publishing:
        error = "no messages received"
    elif not age_ok:
        error = f"stale (age {age_s:.2f}s > {max_age_s:.2f}s)"
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
    registry = topic_registry()
    topics = topic_env()
    max_age_s = float(os.getenv("WAREHOUSE_TOPIC_MAX_AGE_S", "3.0"))
    min_hz = float(os.getenv("WAREHOUSE_TOPIC_MIN_HZ", "0.5"))
    target_keys = keys or list(topics.keys())
    results: dict[str, TopicDiagnostic] = {}
    with ThreadPoolExecutor(max_workers=min(6, len(target_keys) or 1)) as pool:
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
                )
    return results


def _tf_echo_ok(parent: str, child: str, *, timeout_s: float = 1.5) -> bool:
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
    odom_topic = os.getenv("WAREHOUSE_GAZEBO_ODOM_TOPIC", "/warehouse/drone/odometry")
    timeout_s = float(os.getenv("WAREHOUSE_GAZEBO_PROBE_TIMEOUT_S", "3.0"))
    rgb = probe_gazebo_publishing(rgb_topic, timeout_s=timeout_s)
    odom = probe_gazebo_publishing(odom_topic, timeout_s=timeout_s)
    partition = os.getenv("GZ_PARTITION", "").strip() or None
    return {
        "partition": partition,
        "rgb_topic": rgb_topic,
        "odom_topic": odom_topic,
        "rgb_publishing": rgb,
        "odom_publishing": odom,
        "sim_publishing": rgb and odom,
    }


def probe_tf_chain() -> TfChainDiagnostic:
    frames = topic_registry().frames
    odom = frames.get("odom", "odom")
    base_link = frames.get("base_link", "base_link")
    camera = frames.get("camera", "front_rgbd_camera_link")
    odom_base = _tf_echo_ok(odom, base_link)
    base_camera = _tf_echo_ok(base_link, camera)
    chain_ok = odom_base and base_camera
    parts: list[str] = []
    if not odom_base:
        parts.append(f"{odom}->{base_link} missing")
    if not base_camera:
        parts.append(f"{base_link}->{camera} missing")
    detail = "ok" if chain_ok else "; ".join(parts)
    return TfChainDiagnostic(
        odom_frame=odom,
        base_link_frame=base_link,
        camera_frame=camera,
        odom_to_base_link=odom_base,
        base_link_to_camera=base_camera,
        chain_ok=chain_ok,
        detail=detail,
    )


def summarize_diagnostics(
    diagnostics: dict[str, TopicDiagnostic],
) -> dict[str, Any]:
    registry = topic_registry()

    def _healthy(key: str) -> bool:
        diag = diagnostics.get(key)
        return bool(diag and diag.healthy)

    missing_required = [key for key in registry.required_for_perception if not _healthy(key)]
    camera_ok = _healthy("rgb_image") or (
        _healthy("left_image") and _healthy("right_image")
    )
    if camera_ok:
        missing_required = [key for key in missing_required if key != "rgb_image"]
    nvblox_any = any(_healthy(key) for key in registry.required_for_nvblox_any)
    missing_nvblox = (
        [key for key in registry.required_for_nvblox_any if not _healthy(key)]
        if not nvblox_any
        else []
    )
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
            for key, diag in diagnostics.items()
        },
    }
