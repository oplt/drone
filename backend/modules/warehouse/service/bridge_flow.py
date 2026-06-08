from __future__ import annotations

from dataclasses import dataclass

from backend.core.config.runtime import env_truthy, settings


@dataclass(frozen=True)
class WarehouseBridgeFlow:
    name: str
    ros_profile: str
    gazebo_sim: bool = False


def resolve_warehouse_bridge_flow() -> WarehouseBridgeFlow:
    name = settings.WAREHOUSE_BRIDGE_FLOW.strip().lower() or "disabled"
    profile = (settings.warehouse_ros_profile or name).strip() or name
    gazebo = name in {"gazebo", "gz", "simulation", "sim"} or env_truthy(
        settings.warehouse_gazebo_sim
    )
    return WarehouseBridgeFlow(name=name, ros_profile=profile, gazebo_sim=gazebo)


def flow_env_overrides(flow: WarehouseBridgeFlow) -> dict[str, str]:
    return {
        "WAREHOUSE_BRIDGE_FLOW": flow.name,
        "WAREHOUSE_ROS_PROFILE": flow.ros_profile,
        "WAREHOUSE_GAZEBO_SIM": "1" if flow.gazebo_sim else "0",
    }

