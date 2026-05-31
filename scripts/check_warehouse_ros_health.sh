#!/usr/bin/env bash
# Quick ROS-side health check for warehouse Gazebo mapping.
set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export ROS_DISTRO="${ROS_DISTRO:-jazzy}"

source "/opt/ros/${ROS_DISTRO}/setup.bash"
if [ -f "${ROOT}/warehouse_ros2_ws/install/setup.bash" ]; then
  source "${ROOT}/warehouse_ros2_ws/install/setup.bash"
fi

echo "=== Warehouse ROS health ==="
echo "ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
echo "ros_gz_bridge_count=$(pgrep -fc '[r]os_gz_bridge/parameter_bridge' || echo 0)"
echo

echo "=== Gazebo topics (warehouse/imu/odom) ==="
if command -v gz >/dev/null 2>&1; then
  gz topic -l 2>/dev/null | grep -E 'warehouse|imu|odometry' | sort || true
else
  echo "gz CLI not found"
fi
echo

echo "=== ROS topics (warehouse/imu/odom/nvblox) ==="
ros2 topic list --no-daemon 2>/dev/null | grep -E 'warehouse|imu|odom|nvblox' | sort || true
echo

TOPICS=(
  /warehouse/front/rgbd/image
  /warehouse/front/rgbd/depth_image
  /warehouse/front/rgbd/points
  /warehouse/drone/odometry
  /warehouse/local_odometry
)

for topic in "${TOPICS[@]}"; do
  echo "=== ros2 topic info ${topic} ==="
  ros2 topic info "${topic}" --no-daemon 2>&1 || true
  echo
done

echo "=== ROS hz (5s window) ==="
for topic in "${TOPICS[@]}"; do
  printf '%s: ' "${topic}"
  timeout 5 ros2 topic hz "${topic}" 2>&1 | tail -1 || echo "no messages"
  echo
done

if [ -n "${WAREHOUSE_ROS_BRIDGE_URL:-}" ]; then
  echo "=== Bridge /health (deep) ==="
  curl -fsS --max-time 20 "${WAREHOUSE_ROS_BRIDGE_URL}/health?deep=1" | python3 -m json.tool 2>/dev/null | head -80 || true
fi
