from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.core.config.runtime import env_truthy, settings


@dataclass(frozen=True, slots=True)
class WarehouseBridgeFlow:
    name: str
    ros_profile: str
    gazebo_sim: bool = False


def _setting_text(*names: str, default: str = "") -> str:
    """Read a possibly-missing runtime setting as stripped text."""
    for name in names:
        value = getattr(settings, name, None)
        if value is not None:
            return str(value).strip()
    return default


def _truthy(value: Any) -> bool:
    """Accept bools and string-like values without raising on None."""
    if isinstance(value, bool):
        return value
    return env_truthy(str(value or ""))


def resolve_warehouse_bridge_flow() -> WarehouseBridgeFlow:
    raw_name = _setting_text("WAREHOUSE_BRIDGE_FLOW", "warehouse_bridge_flow")
    name = raw_name.lower() or "disabled"

    # Keep profile casing as configured because it may map to an external profile name.
    profile = _setting_text("warehouse_ros_profile", "WAREHOUSE_ROS_PROFILE") or name

    gazebo_value = getattr(
        settings,
        "warehouse_gazebo_sim",
        getattr(settings, "WAREHOUSE_GAZEBO_SIM", False),
    )
    gazebo = name in {"gazebo", "gz", "simulation", "sim"} or _truthy(gazebo_value)

    return WarehouseBridgeFlow(name=name, ros_profile=profile, gazebo_sim=gazebo)


def flow_env_overrides(flow: WarehouseBridgeFlow) -> dict[str, str]:
    return {
        "WAREHOUSE_BRIDGE_FLOW": str(flow.name),
        "WAREHOUSE_ROS_PROFILE": str(flow.ros_profile),
        "WAREHOUSE_GAZEBO_SIM": "1" if flow.gazebo_sim else "0",
    }
