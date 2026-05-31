#!/usr/bin/env bash
# Start nvblox for Gazebo warehouse mapping (RGBD + TF odometry).
set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export AMENT_TRACE_SETUP_FILES="${AMENT_TRACE_SETUP_FILES:-}"

if [ -n "${VIRTUAL_ENV:-}" ]; then
  PATH="${PATH//$VIRTUAL_ENV\/bin:/}"
  PATH="${PATH//:$VIRTUAL_ENV\/bin/}"
  PATH="${PATH//$VIRTUAL_ENV\/bin/}"
  unset VIRTUAL_ENV
fi
unset PYTHONPATH PYTHONHOME

source "/opt/ros/${ROS_DISTRO:-jazzy}/setup.bash"
source "${ROOT}/warehouse_ros2_ws/install/setup.bash"

RGB_TOPIC="${WAREHOUSE_RGB_TOPIC:-/warehouse/front/rgbd/image}"
DEPTH_TOPIC="${WAREHOUSE_DEPTH_TOPIC:-/warehouse/front/rgbd/depth_image}"
ODOM_TOPIC="${WAREHOUSE_VISUAL_SLAM_ODOM_TOPIC:-/warehouse/drone/odometry}"
BASE_LINK_FRAME="${WAREHOUSE_BASE_LINK_FRAME:-base_link}"
WAIT_S="${WAREHOUSE_NVBLOX_SENSOR_WAIT_S:-120}"

_ros_topic_listed() {
  local topic="$1"
  local attempt
  for attempt in 1 2 3; do
    if ros2 topic list 2>/dev/null | grep -Fxq "${topic}"; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

_sensors_ready() {
  _ros_topic_listed "${RGB_TOPIC}" \
    && _ros_topic_listed "${DEPTH_TOPIC}" \
    && _ros_topic_listed "${ODOM_TOPIC}"
}

echo "[warehouse_nvblox] waiting for sensor topics (up to ${WAIT_S}s) ROS_DOMAIN_ID=${ROS_DOMAIN_ID}..."
deadline=$((SECONDS + WAIT_S))
while (( SECONDS < deadline )); do
  if _sensors_ready; then
    echo "[warehouse_nvblox] sensors listed: rgb depth odom"
    break
  fi
  sleep 1
done

if ! _sensors_ready; then
  echo "[warehouse_nvblox] ERROR: required topics missing (rgb=${RGB_TOPIC} depth=${DEPTH_TOPIC} odom=${ODOM_TOPIC}) — start Gazebo + gazebo_sensor_bridge" >&2
  ros2 topic list 2>/dev/null | grep -E 'warehouse|imu|odom' | head -20 >&2 || true
  exit 1
fi

_ensure_sim_tf() {
  if pgrep -f "[w]arehouse_sim_tf_broadcaster" >/dev/null 2>&1; then
    echo "[warehouse_nvblox] warehouse_sim_tf_broadcaster already running"
    return 0
  fi
  echo "[warehouse_nvblox] starting warehouse_sim_tf_broadcaster (required for base_link TF)"
  ros2 run warehouse_mapping_bridge warehouse_sim_tf_broadcaster &
  local wait_deadline=$((SECONDS + 8))
  while (( SECONDS < wait_deadline )); do
    if ros2 topic info "${ODOM_TOPIC}" 2>/dev/null | grep -q "Publisher count: [1-9]"; then
      sleep 0.5
      return 0
    fi
    sleep 0.5
  done
  echo "[warehouse_nvblox] WARN: sim_tf started but odometry publishers not confirmed yet" >&2
}

_ensure_sim_tf

_ensure_odometry_export() {
  if pgrep -f "[w]arehouse_odometry_export" >/dev/null 2>&1; then
    echo "[warehouse_nvblox] warehouse_odometry_export already running"
    return 0
  fi
  echo "[warehouse_nvblox] starting warehouse_odometry_export (live odometry state for safety)"
  ros2 run warehouse_mapping_bridge warehouse_odometry_export &
}

_ensure_odometry_export

if pgrep -f "[n]vblox_ros.*nvblox_node" >/dev/null 2>&1; then
  echo "[warehouse_nvblox] nvblox_node already running — reusing"
  exec tail -f /dev/null
fi

echo "[warehouse_nvblox] starting nvblox_node ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"

exec ros2 run nvblox_ros nvblox_node --ros-args \
  -p num_cameras:=1 \
  -p mapping_type:=static_tsdf \
  -p use_depth:=true \
  -p use_color:=true \
  -p use_lidar:=false \
  -p use_tf_transforms:=true \
  -p global_frame:=odom \
  -p map_clearing_frame_id:=${BASE_LINK_FRAME} \
  -p print_rates_to_console:=false \
  -r camera_0/depth/image:=${DEPTH_TOPIC} \
  -r camera_0/depth/camera_info:=/warehouse/front/rgbd/camera_info \
  -r camera_0/color/image:=${RGB_TOPIC} \
  -r camera_0/color/camera_info:=/warehouse/front/rgbd/camera_info
