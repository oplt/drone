#!/usr/bin/env bash
# Start nvblox for Gazebo warehouse mapping (RGB-D + optional 3D LiDAR + TF odometry).
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
LIDAR_TOPIC="${WAREHOUSE_LIDAR_POINTS_TOPIC:-${WAREHOUSE_RAW_LIDAR_TOPIC:-/warehouse/mid360/scan/points}}"
NVBLOX_USE_LIDAR="${WAREHOUSE_NVBLOX_USE_LIDAR:-1}"
BASE_LINK_FRAME="${WAREHOUSE_BASE_LINK_FRAME:-base_link}"
WAIT_S="${WAREHOUSE_NVBLOX_SENSOR_WAIT_S:-45}"
WAREHOUSE_NVBLOX_TOPIC_HZ_TIMEOUT_S="${WAREHOUSE_NVBLOX_TOPIC_HZ_TIMEOUT_S:-4}"
REQUIRE_LIDAR_HZ="${WAREHOUSE_NVBLOX_REQUIRE_LIDAR_HZ:-1}"
LIDAR_WIDTH="${WAREHOUSE_NVBLOX_LIDAR_WIDTH:-1800}"
LIDAR_HEIGHT="${WAREHOUSE_NVBLOX_LIDAR_HEIGHT:-16}"
LIDAR_VERTICAL_FOV_RAD="${WAREHOUSE_NVBLOX_LIDAR_VERTICAL_FOV_RAD:-1.57}"

children=()

cleanup() {
  for pid in "${children[@]:-}"; do
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}

trap cleanup EXIT

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

_ros_topic_publishing() {
  local topic="$1"
  if timeout "${WAREHOUSE_NVBLOX_TOPIC_HZ_TIMEOUT_S}" \
    ros2 topic hz "${topic}" --window 2 2>/dev/null | grep -q "average rate"; then
    return 0
  fi
  # Sim-time / bridge load: hz can fail while Gazebo is publishing.
  timeout 2 ros2 topic info "${topic}" 2>/dev/null | grep -qE 'Publisher count: [1-9]'
}

_core_sensors_publishing() {
  _ros_topic_publishing "${RGB_TOPIC}" \
    && _ros_topic_publishing "${DEPTH_TOPIC}" \
    && _ros_topic_publishing "${ODOM_TOPIC}"
}

_lidar_publishing() {
  _ros_topic_listed "${LIDAR_TOPIC}" && _ros_topic_publishing "${LIDAR_TOPIC}"
}

_sensors_ready() {
  _ros_topic_listed "${RGB_TOPIC}" \
    && _ros_topic_listed "${DEPTH_TOPIC}" \
    && _ros_topic_listed "${ODOM_TOPIC}"
}

echo "[warehouse_nvblox] waiting for sensor topics publishing (up to ${WAIT_S}s) ROS_DOMAIN_ID=${ROS_DOMAIN_ID} use_lidar=${NVBLOX_USE_LIDAR}..."
deadline=$((SECONDS + WAIT_S))

_last_wait_log=0
while (( SECONDS < deadline )); do
  if _sensors_ready && _core_sensors_publishing; then
    break
  fi
  if (( SECONDS - _last_wait_log >= 5 )); then
    _last_wait_log=$SECONDS
    echo "[warehouse_nvblox] still waiting for sensors (Gazebo Play / gz sim -r) rgb=${RGB_TOPIC} depth=${DEPTH_TOPIC} odom=${ODOM_TOPIC}" >&2
  fi
  sleep 1
done

if ! _sensors_ready; then
  echo "[warehouse_nvblox] ERROR: required topics missing (rgb=${RGB_TOPIC} depth=${DEPTH_TOPIC} odom=${ODOM_TOPIC})" >&2
  echo "[warehouse_nvblox] Start bridge stack (make local-dev) and Gazebo Play, then verify ros2 topic list" >&2
  ros2 topic list 2>/dev/null | grep -E 'warehouse|imu|odom|mid360|scan' | head -40 >&2 || true
  exit 1
fi

if ! _core_sensors_publishing; then
  echo "[warehouse_nvblox] ERROR: RGB/depth/odom exist but are not publishing on ROS" >&2
  echo "[warehouse_nvblox] gz topic -l is not enough — need ros_gz_bridge + Gazebo Play (gz sim -r)" >&2
  exit 1
fi

echo "[warehouse_nvblox] core sensors publishing: rgb depth odom"

if [ "${NVBLOX_USE_LIDAR}" = "1" ]; then
  if [ "${REQUIRE_LIDAR_HZ}" = "1" ] && ! _lidar_publishing; then
    echo "[warehouse_nvblox] WARN: LiDAR ${LIDAR_TOPIC} not publishing yet; starting nvblox depth-only (set WAREHOUSE_NVBLOX_USE_LIDAR=0 to skip)" >&2
    NVBLOX_USE_LIDAR=0
  elif _lidar_publishing; then
    echo "[warehouse_nvblox] LiDAR publishing: ${LIDAR_TOPIC}"
  else
    echo "[warehouse_nvblox] LiDAR listed; nvblox will use ${LIDAR_TOPIC} when stream starts"
  fi
fi


_ensure_sim_tf() {
  if pgrep -f "[w]arehouse_sim_tf_broadcaster" >/dev/null 2>&1; then
    echo "[warehouse_nvblox] warehouse_sim_tf_broadcaster already running"
    return 0
  fi
  echo "[warehouse_nvblox] starting warehouse_sim_tf_broadcaster (required for base_link TF)"
  ros2 run warehouse_mapping_bridge warehouse_sim_tf_broadcaster &
  children+=("$!")
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
  children+=("$!")
}

_ensure_odometry_export

mapfile -t _nvblox_pids < <(pgrep -f "[n]vblox_ros.*nvblox_node" 2>/dev/null || true)
if ((${#_nvblox_pids[@]} > 0)); then
  if ((${#_nvblox_pids[@]} > 1)); then
    echo "[warehouse_nvblox] WARN: ${#_nvblox_pids[@]} nvblox_node processes (duplicate names confuse ROS); stopping all"
    for pid in "${_nvblox_pids[@]}"; do
      kill "${pid}" 2>/dev/null || true
    done
    sleep 1.5
  elif [ "${WAREHOUSE_NVBLOX_REUSE_RUNNING:-1}" = "1" ]; then
    echo "[warehouse_nvblox] nvblox_node already running — reusing pid=${_nvblox_pids[0]}"
    tail -f /dev/null &
    tail_pid="$!"
    children+=("${tail_pid}")
    wait "${tail_pid}"
  fi
fi

echo "[warehouse_nvblox] starting nvblox_node ROS_DOMAIN_ID=${ROS_DOMAIN_ID} use_lidar=${NVBLOX_USE_LIDAR} pointcloud:=${LIDAR_TOPIC}"

CAMERA_INFO_TOPIC="${WAREHOUSE_CAMERA_INFO_TOPIC:-/warehouse/front/rgbd/camera_info}"

_lidar_enabled="false"
if [ "${NVBLOX_USE_LIDAR}" = "1" ]; then
  _lidar_enabled="true"
fi

NVBLOX_ARGS=(
  -p num_cameras:=1
  -p mapping_type:=static_tsdf
  -p use_depth:=true
  -p use_color:=true
  -p use_lidar:="${_lidar_enabled}"
  -p use_tf_transforms:=true
  -p global_frame:=odom
  -p map_clearing_frame_id:="${BASE_LINK_FRAME}"
  -p print_rates_to_console:=false
  -r camera_0/depth/image:="${DEPTH_TOPIC}"
  -r camera_0/depth/camera_info:="${CAMERA_INFO_TOPIC}"
  -r camera_0/color/image:="${RGB_TOPIC}"
  -r camera_0/color/camera_info:="${CAMERA_INFO_TOPIC}"
)

if [ "${NVBLOX_USE_LIDAR}" = "1" ]; then
  NVBLOX_ARGS+=(
    -p lidar_width:="${LIDAR_WIDTH}"
    -p lidar_height:="${LIDAR_HEIGHT}"
    -p lidar_vertical_fov_rad:="${LIDAR_VERTICAL_FOV_RAD}"
    -r pointcloud:="${LIDAR_TOPIC}"
  )
fi

ros2 run nvblox_ros nvblox_node --ros-args "${NVBLOX_ARGS[@]}" &

nvblox_pid="$!"
children+=("${nvblox_pid}")

if [ "${WAREHOUSE_LIVE_MAP_PUBLISH:-1}" = "1" ]; then
  if ! pgrep -f "[w]arehouse_live_map_publisher" >/dev/null 2>&1; then
    echo "[warehouse_nvblox] starting warehouse_live_map_publisher flight=${WAREHOUSE_ACTIVE_FLIGHT_ID:-unknown}"
    ros2 run warehouse_mapping_bridge warehouse_live_map_publisher &
    children+=("$!")
  else
    echo "[warehouse_nvblox] warehouse_live_map_publisher already running"
  fi
fi

wait "${nvblox_pid}"
