from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WarehouseBridgeFlow:
    name: str
    ros_profile: str
    gazebo_sim: bool = False


def resolve_warehouse_bridge_flow() -> WarehouseBridgeFlow:
    name = os.getenv("WAREHOUSE_BRIDGE_FLOW", "disabled").strip().lower() or "disabled"
    profile = os.getenv("WAREHOUSE_ROS_PROFILE", name).strip() or name
    gazebo = name in {"gazebo", "gz", "simulation", "sim"} or os.getenv(
        "WAREHOUSE_GAZEBO_SIM", ""
    ).strip().lower() in {"1", "true", "yes", "on"}
    return WarehouseBridgeFlow(name=name, ros_profile=profile, gazebo_sim=gazebo)


def flow_env_overrides(flow: WarehouseBridgeFlow) -> dict[str, str]:
    return {
        "WAREHOUSE_BRIDGE_FLOW": flow.name,
        "WAREHOUSE_ROS_PROFILE": flow.ros_profile,
        "WAREHOUSE_GAZEBO_SIM": "1" if flow.gazebo_sim else "0",
    }

