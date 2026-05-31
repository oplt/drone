#!/usr/bin/env bash
set -euo pipefail

# Default ROS / warehouse bridge environment.
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export ROS_DISTRO="${ROS_DISTRO:-jazzy}"
export ROS_WS_SETUP="${ROS_WS_SETUP:-warehouse_ros2_ws/install/setup.bash}"
export WAREHOUSE_GAZEBO_SIM="${WAREHOUSE_GAZEBO_SIM:-1}"
export WAREHOUSE_TOPIC_PROFILE="${WAREHOUSE_TOPIC_PROFILE:-gazebo}"
export WAREHOUSE_ROS_PROFILE="${WAREHOUSE_ROS_PROFILE:-gazebo}"

# Make the local warehouse_mapping_bridge Python package importable.
export PYTHONPATH="${PWD}/warehouse_ros2_ws/src/warehouse_mapping_bridge:${PYTHONPATH:-}"

BRIDGE_PYTHON="${WAREHOUSE_BRIDGE_PYTHON:-python3}"

echo "[warehouse_bridge] start app_python=$(${BRIDGE_PYTHON} -V 2>&1) profile=${WAREHOUSE_TOPIC_PROFILE} WAREHOUSE_ROS_BRIDGE_URL=${WAREHOUSE_ROS_BRIDGE_URL:-unset} WAREHOUSE_ROS_WS_URL=${WAREHOUSE_ROS_WS_URL:-unset} ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"

exec "${BRIDGE_PYTHON}" -m warehouse_mapping_bridge.bridge_service
