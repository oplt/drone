#!/usr/bin/env bash
# Source this in any shell before ros2/gz warehouse commands:
#   source /path/to/drone_app/scripts/source_warehouse_ros.sh
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export ROS_DISTRO="${ROS_DISTRO:-jazzy}"
source "/opt/ros/${ROS_DISTRO}/setup.bash"
if [ -f "${ROOT}/warehouse_ros2_ws/install/setup.bash" ]; then
  source "${ROOT}/warehouse_ros2_ws/install/setup.bash"
fi
echo "warehouse ROS env: ROS_DOMAIN_ID=${ROS_DOMAIN_ID} (bridge/backend use 42 — not domain 0)"
