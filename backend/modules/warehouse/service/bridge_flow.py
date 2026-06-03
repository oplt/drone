from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

WarehouseBridgeFlowName = Literal["gazebo", "isaac", "real_device"]


@dataclass(frozen=True)
class WarehouseBridgeFlow:
    name: WarehouseBridgeFlowName
    ros_profile: str
    topic_profile: str
    launch_file: str
    gazebo_sim: bool
    use_sim_time: bool
    video_uses_gazebo: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "ros_profile": self.ros_profile,
            "topic_profile": self.topic_profile,
            "launch_file": self.launch_file,
            "gazebo_sim": self.gazebo_sim,
            "use_sim_time": self.use_sim_time,
            "video_uses_gazebo": self.video_uses_gazebo,
        }


_FLOWS: dict[WarehouseBridgeFlowName, WarehouseBridgeFlow] = {
    "gazebo": WarehouseBridgeFlow(
        name="gazebo",
        ros_profile="gazebo",
        topic_profile="gazebo",
        launch_file="gazebo_warehouse_stack.launch.py",
        gazebo_sim=True,
        use_sim_time=True,
        video_uses_gazebo=True,
    ),
    "isaac": WarehouseBridgeFlow(
        name="isaac",
        ros_profile="isaac_ros_nvblox_stereo",
        topic_profile="isaac_ros_nvblox_stereo",
        launch_file="isaac_warehouse_mapping.launch.py",
        gazebo_sim=False,
        use_sim_time=False,
        video_uses_gazebo=False,
    ),
    "real_device": WarehouseBridgeFlow(
        name="real_device",
        ros_profile="real_device",
        topic_profile="real_device",
        launch_file="real_device_warehouse_mapping.launch.py",
        gazebo_sim=False,
        use_sim_time=False,
        video_uses_gazebo=False,
    ),
}


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_flow(value: str) -> WarehouseBridgeFlowName | None:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"real", "device", "real_drone", "hardware"}:
        return "real_device"
    if normalized in {"gazebo", "sim", "simulation"}:
        return "gazebo"
    if normalized in {"isaac", "isaac_ros", "nvblox", "isaac_ros_nvblox_stereo"}:
        return "isaac"
    if normalized in _FLOWS:
        return normalized  # type: ignore[return-value]
    return None


def _setting_value(name: str) -> str:
    try:
        from backend.core.config.runtime import settings

        return str(getattr(settings, name, "") or "")
    except Exception:
        return ""


def _env_or_setting(name: str) -> str:
    return os.getenv(name, "").strip() or _setting_value(name).strip()


def resolve_warehouse_bridge_flow() -> WarehouseBridgeFlow:
    explicit = _normalize_flow(_env_or_setting("WAREHOUSE_BRIDGE_FLOW"))
    if explicit is not None:
        return _FLOWS[explicit]

    topic_profile = _normalize_flow(_env_or_setting("WAREHOUSE_TOPIC_PROFILE"))
    if topic_profile is not None:
        return _FLOWS[topic_profile]

    ros_profile = _normalize_flow(_env_or_setting("WAREHOUSE_ROS_PROFILE"))
    if ros_profile is not None:
        return _FLOWS[ros_profile]

    if _truthy(_env_or_setting("WAREHOUSE_GAZEBO_SIM")):
        return _FLOWS["gazebo"]
    return _FLOWS["isaac"]


def flow_env_overrides(flow: WarehouseBridgeFlow | None = None) -> dict[str, str]:
    selected = flow or resolve_warehouse_bridge_flow()
    env = {
        "WAREHOUSE_BRIDGE_FLOW": selected.name,
        "WAREHOUSE_ROS_PROFILE": selected.ros_profile,
        "WAREHOUSE_TOPIC_PROFILE": selected.topic_profile,
        "WAREHOUSE_GAZEBO_SIM": "1" if selected.gazebo_sim else "0",
        "WAREHOUSE_USE_SIM_TIME": "1" if selected.use_sim_time else "0",
        "DRONE_VIDEO_USE_GAZEBO": "1" if selected.video_uses_gazebo else "0",
    }
    if selected.gazebo_sim:
        env.setdefault("WAREHOUSE_GAZEBO_DIRECT_CONTRACT_BRIDGE", "0")
    if not os.getenv("WAREHOUSE_LOCALIZATION_MODE", "").strip():
        from backend.modules.warehouse.service.localization_mode import (
            localization_mode_env_value,
        )

        env["WAREHOUSE_LOCALIZATION_MODE"] = localization_mode_env_value()
    if selected.name == "real_device":
        env.setdefault("WAREHOUSE_SEND_VISION_POSITION", "0")
    backend_url = os.getenv("WAREHOUSE_BACKEND_URL", "").strip()
    if backend_url:
        env.setdefault("WAREHOUSE_BACKEND_URL", backend_url)
    ingest_token = os.getenv("WAREHOUSE_LIVE_MAP_INGEST_TOKEN", "").strip()
    if ingest_token:
        env.setdefault("WAREHOUSE_LIVE_MAP_INGEST_TOKEN", ingest_token)
    return env
