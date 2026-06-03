#!/usr/bin/env bash
# Start ros_gz_bridge once external Gazebo lists warehouse sensor topics.
# Gazebo is started externally, e.g. gz sim -v4 -r iriswlidar_warehouse.sdf
set -eo pipefail

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export ROS_DISTRO="${ROS_DISTRO:-jazzy}"
export WAREHOUSE_GAZEBO_BRIDGE_LOG_LEVEL="${WAREHOUSE_GAZEBO_BRIDGE_LOG_LEVEL:-info}"
export AMENT_TRACE_SETUP_FILES="${AMENT_TRACE_SETUP_FILES:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -n "${VIRTUAL_ENV:-}" ]; then
  PATH="${PATH//$VIRTUAL_ENV\/bin:/}"
  PATH="${PATH//:$VIRTUAL_ENV\/bin/}"
  PATH="${PATH//$VIRTUAL_ENV\/bin/}"
  unset VIRTUAL_ENV
fi
PATH="${PATH//$REPO_ROOT\/.venv\/bin:/}"
PATH="${PATH//:$REPO_ROOT\/.venv\/bin/}"
PATH="${PATH//$REPO_ROOT\/.venv\/bin/}"
PATH="${PATH//$REPO_ROOT\/backend\/.venv\/bin:/}"
PATH="${PATH//:$REPO_ROOT\/backend\/.venv\/bin/}"
PATH="${PATH//$REPO_ROOT\/backend\/.venv\/bin/}"
export PATH
unset PYTHONPATH PYTHONHOME

source "/opt/ros/${ROS_DISTRO}/setup.bash"

BRIDGE_MATCH='[r]os_gz_bridge/parameter_bridge.*/warehouse/front/rgbd/image'
REUSE_EXISTING_BRIDGE="${WAREHOUSE_REUSE_EXISTING_GAZEBO_BRIDGE:-0}"

if pgrep -f "${BRIDGE_MATCH}" >/dev/null 2>&1; then
  RGB_TOPIC="${WAREHOUSE_GAZEBO_RGB_TOPIC:-/warehouse/front/rgbd/image}"

  if [ "${REUSE_EXISTING_BRIDGE}" = "1" ] && timeout 2 ros2 topic info "${RGB_TOPIC}" >/dev/null 2>&1; then
    echo "[gazebo_sensor_bridge] bridge already running with ${RGB_TOPIC}; keeping it"
    exit 0
  fi

  echo "[gazebo_sensor_bridge] stopping existing ros_gz_bridge instances..."
  pkill -f "${BRIDGE_MATCH}" || true
  sleep 1
fi

RGB_TOPIC="${WAREHOUSE_GAZEBO_RGB_TOPIC:-/warehouse/front/rgbd/image}"
DEPTH_TOPIC="${WAREHOUSE_GAZEBO_DEPTH_TOPIC:-/warehouse/front/rgbd/depth_image}"
POINTS_TOPIC="${WAREHOUSE_GAZEBO_POINTS_TOPIC:-/warehouse/front/rgbd/points}"
CAMERA_INFO_TOPIC="${WAREHOUSE_CAMERA_INFO_TOPIC:-/warehouse/front/rgbd/camera_info}"
ODOM_TOPIC="${WAREHOUSE_GAZEBO_ODOM_TOPIC:-/warehouse/drone/odometry}"
WAIT_S="${WAREHOUSE_GAZEBO_SENSOR_WAIT_S:-300}"
REQUIRE_PUBLISHING="${WAREHOUSE_GAZEBO_REQUIRE_PUBLISHING:-1}"
MIN_SENSOR_MESSAGES="${WAREHOUSE_GAZEBO_MIN_SENSOR_MESSAGES:-2}"
SENSOR_SAMPLE_S="${WAREHOUSE_GAZEBO_SENSOR_SAMPLE_S:-3}"
REQUIRE_LIDAR_POINTS="${WAREHOUSE_GAZEBO_REQUIRE_LIDAR_POINTS:-0}"

_gazebo_listed() {
  gz topic -l 2>/dev/null | grep -Fxq "$1"
}

_gazebo_publishing() {
  local topic="$1"
  local sample_s="${2:-${SENSOR_SAMPLE_S}}"
  local min_messages="${3:-${MIN_SENSOR_MESSAGES}}"
  local count
  count="$(timeout "${sample_s}" gz topic -t "${topic}" -f 2>/dev/null | sed -n '/^data: /p' | wc -l)"
  if [ "${count}" -lt "${min_messages}" ]; then
    count="$(timeout "${sample_s}" gz topic -t "${topic}" -f 2>/dev/null | awk 'NF {c++} END {print c+0}')"
  fi
  [ "${count}" -ge "${min_messages}" ]
}

_gazebo_sensors_publishing() {
  _gazebo_publishing "${RGB_TOPIC}" "${SENSOR_SAMPLE_S}" "${MIN_SENSOR_MESSAGES}" \
    && _gazebo_publishing "${DEPTH_TOPIC}" "${SENSOR_SAMPLE_S}" "${MIN_SENSOR_MESSAGES}" \
    && _gazebo_publishing "${ODOM_TOPIC}" "${SENSOR_SAMPLE_S}" "${MIN_SENSOR_MESSAGES}" \
    && { [ "${REQUIRE_LIDAR_POINTS}" != "1" ] \
      || _gazebo_publishing "/scan/points" "${SENSOR_SAMPLE_S}" "${MIN_SENSOR_MESSAGES}"; }
}

_discover_imu_topic() {
  local topic="${WAREHOUSE_GAZEBO_IMU_TOPIC:-${WAREHOUSE_IMU_TOPIC:-}}"
  if [ -n "${topic}" ]; then
    echo "${topic}"
    return 0
  fi
  # Prefer the Iris standoff IMU in iris_warehouse (matches ros_gz_bridge default).
  gz topic -l 2>/dev/null | grep -E 'imu_sensor/imu$' | head -1 \
    || gz topic -l 2>/dev/null | grep -iE '/imu$' | grep -E '^/' | head -1 \
    || true
}

echo "[gazebo_sensor_bridge] waiting for external Gazebo on ${RGB_TOPIC} (up to ${WAIT_S}s)..."
deadline=$((SECONDS + WAIT_S))
saw_topic=0
sensors_ok=0
while (( SECONDS < deadline )); do
   if _gazebo_listed "${RGB_TOPIC}"; then
     saw_topic=1

     if _gazebo_sensors_publishing; then
       sensors_ok=1
       echo "[gazebo_sensor_bridge] Gazebo required sensors publishing"
       break
     fi

     echo "[gazebo_sensor_bridge] topic listed but not publishing yet (press Play or use: gz sim -r <world>.sdf)"

     if [ "${REQUIRE_PUBLISHING}" != "1" ]; then
       echo "[gazebo_sensor_bridge] starting bridge anyway; ROS publishers appear once sim publishes"
       break
     fi
   fi
   sleep 2
 done


if [ "${REQUIRE_PUBLISHING}" = "1" ] && [ "${sensors_ok}" != "1" ]; then
  echo "[gazebo_sensor_bridge] ERROR: Gazebo sensors idle after ${WAIT_S}s — start with gz sim -r or press Play" >&2
  echo "[gazebo_sensor_bridge] Verify: gz topic -e -t ${RGB_TOPIC}" >&2
  echo "[gazebo_sensor_bridge] Verify: gz topic -e -t ${DEPTH_TOPIC}" >&2
  echo "[gazebo_sensor_bridge] Verify: gz topic -e -t ${ODOM_TOPIC}" >&2
  if [ "${REQUIRE_LIDAR_POINTS}" = "1" ]; then
    echo "[gazebo_sensor_bridge] Verify: gz topic -e -t /scan/points" >&2
  fi
  exit 1
fi

if [ "${sensors_ok}" != "1" ]; then
  echo "[gazebo_sensor_bridge] WARN: Gazebo not publishing yet; bridge will relay once sim runs"
fi


IMU_TOPIC="$(_discover_imu_topic)"

children=()

cleanup() {
  local sig="${1:-TERM}"
  for pid in "${children[@]:-}"; do
    if [ -n "${pid:-}" ] && kill -0 "${pid}" 2>/dev/null; then
      kill -s "${sig}" "${pid}" 2>/dev/null || true
    fi
  done
}

trap 'cleanup TERM' EXIT
trap 'cleanup INT; exit 130' INT
trap 'cleanup TERM; exit 143' TERM

# ros_gz_bridge mirrors Gazebo-native topic names on ROS; warehouse_topic_adapter
# relays those sources into /warehouse/contract/* for health and flight code.
_gz_bridge_specs=(
  "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"
  "${RGB_TOPIC}@sensor_msgs/msg/Image[gz.msgs.Image"
  "${DEPTH_TOPIC}@sensor_msgs/msg/Image[gz.msgs.Image"
  "${CAMERA_INFO_TOPIC}@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo"
  "${POINTS_TOPIC}@sensor_msgs/msg/PointCloud2[gz.msgs.PointCloudPacked"
  "${ODOM_TOPIC}@nav_msgs/msg/Odometry[gz.msgs.Odometry"
)
_bridge_specs=("${_gz_bridge_specs[@]}")

IMU_RELAY_SOURCE=""
if [ -n "${IMU_TOPIC}" ] && _gazebo_listed "${IMU_TOPIC}"; then
  _bridge_specs+=("${IMU_TOPIC}@sensor_msgs/msg/Imu[gz.msgs.IMU")
  echo "[gazebo_sensor_bridge] IMU bridge ${IMU_TOPIC}"

  if [ "${IMU_TOPIC}" != "/imu" ]; then
    IMU_RELAY_SOURCE="${IMU_TOPIC}"
  fi
elif [ -n "${IMU_TOPIC}" ]; then
  echo "[gazebo_sensor_bridge] WARN: IMU topic not listed yet (${IMU_TOPIC}); using neutral /imu fallback"
  ros2 topic pub /imu sensor_msgs/msg/Imu \
    '{orientation: {w: 1.0}, angular_velocity: {x: 0.0, y: 0.0, z: 0.0}, linear_acceleration: {x: 0.0, y: 0.0, z: 9.81}}' \
    --rate 50 >/tmp/warehouse_imu_pub.log 2>&1 &
  children+=("$!")
else
  echo "[gazebo_sensor_bridge] WARN: no IMU topic configured or discovered; publishing neutral /imu"
  ros2 topic pub /imu sensor_msgs/msg/Imu \
    '{orientation: {w: 1.0}, angular_velocity: {x: 0.0, y: 0.0, z: 0.0}, linear_acceleration: {x: 0.0, y: 0.0, z: 9.81}}' \
    --rate 50 >/tmp/warehouse_imu_pub.log 2>&1 &
  children+=("$!")
fi

if _gazebo_listed "/warehouse/stereo/left/image"; then
  _bridge_specs+=(
    "/warehouse/stereo/left/image@sensor_msgs/msg/Image[gz.msgs.Image"
    "/warehouse/stereo/left/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo"
    "/warehouse/stereo/right/image@sensor_msgs/msg/Image[gz.msgs.Image"
    "/warehouse/stereo/right/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo"
  )
fi

if _gazebo_listed "/scan"; then
  _bridge_specs+=("/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan")
fi

if _gazebo_listed "/scan/points"; then
  _bridge_specs+=("/scan/points@sensor_msgs/msg/PointCloud2[gz.msgs.PointCloudPacked")
fi

echo "[gazebo_sensor_bridge] starting bridge ROS_DOMAIN_ID=${ROS_DOMAIN_ID} bridges=${#_bridge_specs[@]}"

ros2 run ros_gz_bridge parameter_bridge \
  "${_bridge_specs[@]}" \
  --ros-args --log-level "${WAREHOUSE_GAZEBO_BRIDGE_LOG_LEVEL}" &

bridge_pid="$!"
children+=("${bridge_pid}")

_wait_ros_publishers() {
  local topic="$1"
  local wait_s="${2:-15}"
  local deadline=$((SECONDS + wait_s))
  while (( SECONDS < deadline )); do
    if timeout 3 ros2 topic info "${topic}" 2>/dev/null | grep -qE 'Publisher count: [1-9]'; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

_start_imu_source_relay() {
  local src="${1:-}"
  if [ -z "${src}" ] || [ "${src}" = "/imu" ]; then
    return 0
  fi
  _wait_ros_publishers "${src}" 25 \
    || echo "[gazebo_sensor_bridge] WARN: ${src} has no ROS publisher yet; starting /imu relay anyway" >&2
  echo "[gazebo_sensor_bridge] relay ${src} -> /imu (topic_adapter source)"
  ros2 run topic_tools relay "${src}" /imu sensor_msgs/msg/Imu \
    --ros-args -p use_sim_time:=true &
  children+=("$!")
}

# Contract topics (/warehouse/contract/*) are published by warehouse_topic_adapter in the bridge stack.
# Drop stale topic_tools relays so health probes see a single publisher per contract topic.
pkill -f 'topic_tools relay.*warehouse/contract' 2>/dev/null || true

# Sim time: /clock must publish before TF and depth probes can succeed.
if ! _wait_ros_publishers "/clock" 20; then
  echo "[gazebo_sensor_bridge] WARN: /clock not publishing yet; start Gazebo with gz sim -r or press Play" >&2
fi
_wait_ros_publishers "${RGB_TOPIC}" 20 \
  || echo "[gazebo_sensor_bridge] WARN: ${RGB_TOPIC} has no ROS publisher yet; adapter will relay when sim publishes"

if [ -n "${IMU_RELAY_SOURCE}" ]; then
  _start_imu_source_relay "${IMU_RELAY_SOURCE}"
  _wait_ros_publishers "/imu" 20 \
    || echo "[gazebo_sensor_bridge] WARN: /imu has no publisher yet; contract IMU will appear once Gazebo publishes" >&2
fi

# Stay alive while ros_gz_bridge runs.
echo "[gazebo_sensor_bridge] watching ros_gz_bridge pid=${bridge_pid}"
while kill -0 "${bridge_pid}" 2>/dev/null; do
  sleep 2
done
echo "[gazebo_sensor_bridge] ros_gz_bridge exited" >&2
exit 1