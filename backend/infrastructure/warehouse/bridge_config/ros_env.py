from __future__ import annotations

import os
from pathlib import Path

from backend.core.config.runtime import settings


def ros_command_env() -> dict[str, str]:
    env = dict(os.environ)
    env["ROS_DOMAIN_ID"] = ros_domain_id()
    env.setdefault("ROS_LOG_DIR", "/tmp/warehouse_ros_logs")
    # FastDDS shared-memory ports frequently remain locked after Gazebo/ROS
    # restarts in local dev, producing RTPS_TRANSPORT_SHM errors. UDP keeps
    # discovery/data flow reliable for this single-machine sim stack.
    env.setdefault("FASTDDS_BUILTIN_TRANSPORTS", "UDPv4")
    venv_bin = None
    if env.get("VIRTUAL_ENV"):
        venv_bin = str(Path(env["VIRTUAL_ENV"]) / "bin")
    env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    if venv_bin:
        env["PATH"] = ":".join(
            part for part in env.get("PATH", "").split(":") if part != venv_bin
        )
    return env


def configure_embedded_ros_environment() -> None:
    """Apply transport settings before the API process creates an rclpy context.

    CLI probes and launched ROS processes already use ``ros_command_env``. The
    in-process live-map subscribers must use the same DDS domain and transport;
    otherwise FastDDS may select stale shared-memory ports and receive no data.
    """
    env = ros_command_env()
    for name in (
        "ROS_DOMAIN_ID",
        "ROS_AUTOMATIC_DISCOVERY_RANGE",
        "RMW_IMPLEMENTATION",
        "FASTDDS_BUILTIN_TRANSPORTS",
    ):
        value = env.get(name)
        if value:
            os.environ[name] = value


def ros_domain_id() -> str:
    return settings.ros_domain_id
