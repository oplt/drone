#!/usr/bin/env bash
# Verify core warehouse ROS topics publish continuously before flight.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export ROS_DISTRO="${ROS_DISTRO:-jazzy}"

STABLE_MS="${WAREHOUSE_PERCEPTION_REQUIRED_STABLE_MS:-8000}"
STABLE_SECONDS="$(( (STABLE_MS + 999) / 1000 ))"
HZ_TIMEOUT="${WAREHOUSE_TOPIC_HZ_TIMEOUT_S:-2}"
POLL_S="${WAREHOUSE_READINESS_POLL_S:-0.5}"

source "/opt/ros/${ROS_DISTRO}/setup.bash"
if [ -f "${ROOT}/warehouse_ros2_ws/install/setup.bash" ]; then
  source "${ROOT}/warehouse_ros2_ws/install/setup.bash"
fi

echo "ROS_DOMAIN_ID=${ROS_DOMAIN_ID} (must match bridge stack, usually 42)"
echo "Contract topics (health/preflight):"
echo "  /warehouse/contract/rgb/image"
echo "  /warehouse/contract/depth/image"
echo "  /warehouse/contract/odometry"
echo "Gazebo source topics (ros_gz_bridge):"
echo "  /warehouse/front/rgbd/image"
echo "  /warehouse/front/rgbd/depth_image"
echo "  /warehouse/drone/odometry"
echo "  /warehouse/mid360/scan/points (3D LiDAR for nvblox)"
echo

REQUIRED_TOPICS=(
  "${WAREHOUSE_RGB_TOPIC:-/warehouse/contract/rgb/image}"
  "${WAREHOUSE_DEPTH_TOPIC:-/warehouse/contract/depth/image}"
  "${WAREHOUSE_IMU_TOPIC:-/warehouse/contract/imu}"
  "${WAREHOUSE_ODOMETRY_TOPIC:-/warehouse/contract/odometry}"
)

if [ "${WAREHOUSE_NVBLOX_USE_LIDAR:-0}" = "1" ] || [ "${WAREHOUSE_REQUIRE_RAW_LIDAR:-0}" = "1" ]; then
  REQUIRED_TOPICS+=(
    "${WAREHOUSE_RAW_LIDAR_TOPIC:-/warehouse/contract/points}"
  )
fi


_topic_publishing() {
  local topic="$1"
  timeout "${HZ_TIMEOUT}" ros2 topic hz "${topic}" --window 3 --no-daemon 2>/dev/null | grep -q "average rate"
}

_check_all_topics() {
  local failed=0
  for topic in "${REQUIRED_TOPICS[@]}"; do
    if _topic_publishing "${topic}"; then
      echo "OK  ${topic}"
    else
      echo "FAIL ${topic}"
      failed=1
    fi
  done
  return "${failed}"
}

echo "=== Warehouse perception topic stability check ==="
echo "ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
echo "Required stable window: ${STABLE_SECONDS}s"
echo "Topics: ${REQUIRED_TOPICS[*]}"
echo

MAX_WAIT_S="${WAREHOUSE_PERCEPTION_CHECK_MAX_WAIT_S:-60}"

started_at="$(date +%s)"
stable_started=""

while true; do
  now="$(date +%s)"
  total_elapsed=$(( now - started_at ))

  if (( total_elapsed >= MAX_WAIT_S )); then
    echo "ERROR: perception topics did not become stable within ${MAX_WAIT_S}s" >&2
    exit 1
  fi

  if _check_all_topics; then
    if [ -z "${stable_started}" ]; then
      stable_started="${now}"
      echo "-- all topics publishing; stability timer started --"
    else
      elapsed=$(( now - stable_started ))
      echo "-- stable for ${elapsed}s / ${STABLE_SECONDS}s --"

      if (( elapsed >= STABLE_SECONDS )); then
        echo
        echo "Core warehouse perception topics are publishing continuously."
        exit 0
      fi
    fi
  else
    if [ -n "${stable_started}" ]; then
      echo "-- stability reset (topic drop detected) --"
    fi
    stable_started=""
  fi

  sleep "${POLL_S}"
done
