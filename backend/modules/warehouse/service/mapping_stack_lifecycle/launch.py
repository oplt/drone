"""Warehouse mapping stack lifecycle — nvblox ROS launch command builder."""

from __future__ import annotations

import shlex

from . import deps


def _build_nvblox_launch_command() -> list[str]:
    settings = deps.resolve("settings")
    ros_distro = (settings.ROS_DISTRO or "jazzy").strip()

    ros_setup_file = (
        settings.WAREHOUSE_ROS_SETUP_FILE
        or f"/opt/ros/{ros_distro}/setup.bash"
    ).strip()

    workspace_setup_file = (
        settings.WAREHOUSE_ROS_WORKSPACE_SETUP_FILE or ""
    ).strip()

    launch_package = (
        settings.WAREHOUSE_NVBLOX_LAUNCH_PACKAGE
        or "drone_gz_bridge"
    ).strip()

    launch_file = (
        settings.WAREHOUSE_NVBLOX_LAUNCH_FILE
        or "warehouse_nvblox.launch.py"
    ).strip()

    launch_args_raw = (
        settings.WAREHOUSE_NVBLOX_LAUNCH_ARGS
        or (
            "use_sim_time:=true "
            "run_rviz:=false "
            "start_odom_to_tf:=false "
            "start_odom_to_pose:=false "
            "use_tf_transforms:=true "
            "use_topic_transforms:=false "
            "input_qos:=SENSOR_DATA "
            "global_frame:=odom "
            "pose_frame:=base_link "
            "use_lidar:=false "
            "use_rgbd:=true"
        )
    ).strip()

    launch_args = shlex.split(launch_args_raw)

    if not launch_package:
        raise RuntimeError("WAREHOUSE_NVBLOX_LAUNCH_PACKAGE is empty.")

    if not launch_file:
        raise RuntimeError("WAREHOUSE_NVBLOX_LAUNCH_FILE is empty.")

    ros2_launch_cmd = [
        "ros2",
        "launch",
        launch_package,
        launch_file,
        *launch_args,
    ]

    script_parts: list[str] = []

    if ros_setup_file:
        script_parts.append(f"source {shlex.quote(ros_setup_file)}")

    if workspace_setup_file:
        script_parts.append(f"source {shlex.quote(workspace_setup_file)}")

    script_parts.append(
        "exec " + " ".join(shlex.quote(part) for part in ros2_launch_cmd)
    )

    return ["bash", "-lc", " && ".join(script_parts)]


__all__ = ["_build_nvblox_launch_command"]
