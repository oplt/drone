from __future__ import annotations

import os

from rclpy.exceptions import ParameterAlreadyDeclaredException
from rclpy.node import Node
from rclpy.parameter import Parameter


def use_sim_time_from_env() -> bool:
    return os.getenv("WAREHOUSE_USE_SIM_TIME", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def configure_use_sim_time(node: Node, *, default: bool | None = None) -> bool:
    """Set use_sim_time without conflicting with rclpy's built-in declaration."""
    value = use_sim_time_from_env() if default is None else default
    if node.has_parameter("use_sim_time"):
        node.set_parameters([Parameter("use_sim_time", Parameter.Type.BOOL, value)])
        return value
    try:
        node.declare_parameter("use_sim_time", value)
    except ParameterAlreadyDeclaredException:
        node.set_parameters([Parameter("use_sim_time", Parameter.Type.BOOL, value)])
    return value
