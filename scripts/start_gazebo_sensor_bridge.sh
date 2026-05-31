#!/usr/bin/env bash
# Start ros_gz_bridge once external Gazebo lists warehouse sensor topics.
# Gazebo is started externally, e.g. gz sim -v4 -r iriswlidar_warehouse.sdf
set -eo pipefail

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export ROS_DISTRO="${ROS_DISTRO:-jazzy}"
export WAREHOUSE_GAZEBO_BRIDGE_LOG_LEVEL="${WAREHOUSE_GAZEBO_BRIDGE_LOG_LEVEL:-info}"
export AMENT_TRACE_SETUP_FILES="${AMENT_TRACE_SETUP_FILES:-}"

if [ -n "${VIRTUAL_ENV:-}" ]; then
  PATH="${PATH//$VIRTUAL_ENV\/bin:/}"
  PATH="${PATH//:$VIRTUAL_ENV\/bin/}"
  PATH="${PATH//$VIRTUAL_ENV\/bin/}"
  unset VIRTUAL_ENV
fi
unset PYTHONPATH PYTHONHOME

source "/opt/ros/${ROS_DISTRO}/setup.bash"

BRIDGE_MATCH='[r]os_gz_bridge/parameter_bridge.*/warehouse/front/rgbd/image'
if pgrep -f "${BRIDGE_MATCH}" >/dev/null 2>&1; then
  echo "[gazebo_sensor_bridge] stopping stale ros_gz_bridge instances..."
  pkill -f "${BRIDGE_MATCH}" || true
  sleep 1
fi

RGB_TOPIC="${WAREHOUSE_GAZEBO_RGB_TOPIC:-/warehouse/front/rgbd/image}"
DEPTH_TOPIC="${WAREHOUSE_GAZEBO_DEPTH_TOPIC:-/warehouse/front/rgbd/depth_image}"
POINTS_TOPIC="${WAREHOUSE_GAZEBO_POINTS_TOPIC:-/warehouse/front/rgbd/points}"
CAMERA_INFO_TOPIC="${WAREHOUSE_GAZEBO_CAMERA_INFO_TOPIC:-/warehouse/front/rgbd/camera_info}"
ODOM_TOPIC="${WAREHOUSE_GAZEBO_ODOM_TOPIC:-/warehouse/drone/odometry}"
WAIT_S="${WAREHOUSE_GAZEBO_SENSOR_WAIT_S:-300}"
REQUIRE_PUBLISHING="${WAREHOUSE_GAZEBO_REQUIRE_PUBLISHING:-1}"

_gazebo_listed() {
  gz topic -l 2>/dev/null | grep -Fxq "$1"
}

_gazebo_publishing() {
  timeout "${2:-3}" gz topic -t "$1" -f 2>/dev/null | grep -q .
}

_gazebo_sensors_publishing() {
  _gazebo_publishing "${RGB_TOPIC}" 3 \
    && _gazebo_publishing "${DEPTH_TOPIC}" 3 \
    && _gazebo_publishing "${ODOM_TOPIC}" 3
}

_discover_imu_topic() {
  local topic="${WAREHOUSE_GAZEBO_IMU_TOPIC:-${WAREHOUSE_IMU_TOPIC:-}}"
  if [ -n "${topic}" ]; then
    echo "${topic}"
    return 0
  fi
  gz topic -l 2>/dev/null | grep -iE 'imu' | grep -E '^/' | head -1 || true
}

echo "[gazebo_sensor_bridge] waiting for external Gazebo on ${RGB_TOPIC} (up to ${WAIT_S}s)..."
deadline=$((SECONDS + WAIT_S))
saw_topic=0
while (( SECONDS < deadline )); do
  if _gazebo_listed "${RGB_TOPIC}"; then
    saw_topic=1
    if _gazebo_sensors_publishing; then
      echo "[gazebo_sensor_bridge] Gazebo RGB, depth, and odometry publishing"
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

if ! _gazebo_listed "${RGB_TOPIC}"; then
  if (( saw_topic == 0 )); then
    echo "[gazebo_sensor_bridge] ERROR: ${RGB_TOPIC} not found — start external Gazebo first" >&2
  else
    echo "[gazebo_sensor_bridge] ERROR: ${RGB_TOPIC} listed but never published within ${WAIT_S}s" >&2
  fi
  exit 1
fi

if [ "${REQUIRE_PUBLISHING}" = "1" ] && ! _gazebo_sensors_publishing; then
  echo "[gazebo_sensor_bridge] ERROR: Gazebo sensors idle after ${WAIT_S}s — start with gz sim -r or press Play" >&2
  echo "[gazebo_sensor_bridge] Verify: gz topic -e -t ${RGB_TOPIC}" >&2
  echo "[gazebo_sensor_bridge] Verify: gz topic -e -t ${DEPTH_TOPIC}" >&2
  echo "[gazebo_sensor_bridge] Verify: gz topic -e -t ${ODOM_TOPIC}" >&2
  exit 1
fi

if ! _gazebo_sensors_publishing; then
  echo "[gazebo_sensor_bridge] WARN: Gazebo not publishing yet; bridge will relay once sim runs"
fi

IMU_TOPIC="$(_discover_imu_topic)"

_bridge_specs=(
  "${RGB_TOPIC}@sensor_msgs/msg/Image[gz.msgs.Image"
  "${DEPTH_TOPIC}@sensor_msgs/msg/Image[gz.msgs.Image"
  "${CAMERA_INFO_TOPIC}@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo"
  "${POINTS_TOPIC}@sensor_msgs/msg/PointCloud2[gz.msgs.PointCloudPacked"
  "${ODOM_TOPIC}@nav_msgs/msg/Odometry[gz.msgs.Odometry"
)

if [ -n "${IMU_TOPIC}" ] && _gazebo_listed "${IMU_TOPIC}"; then
  _bridge_specs+=("${IMU_TOPIC}@sensor_msgs/msg/Imu[gz.msgs.IMU")
  echo "[gazebo_sensor_bridge] IMU bridge ${IMU_TOPIC}"
  if [ "${IMU_TOPIC}" != "/imu" ]; then
    export WAREHOUSE_IMU_RELAY_SOURCE="${IMU_TOPIC}"
  fi
elif [ -n "${IMU_TOPIC}" ]; then
  echo "[gazebo_sensor_bridge] WARN: IMU topic not listed yet (${IMU_TOPIC}); skipping IMU bridge"
else
  echo "[gazebo_sensor_bridge] WARN: no IMU topic configured or discovered; set WAREHOUSE_IMU_TOPIC"
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

if [ -n "${WAREHOUSE_IMU_RELAY_SOURCE:-}" ]; then
  echo "[gazebo_sensor_bridge] starting IMU relay ${WAREHOUSE_IMU_RELAY_SOURCE} -> /imu"
  ros2 run topic_tools relay "${WAREHOUSE_IMU_RELAY_SOURCE}" /imu sensor_msgs/msg/Imu &
  IMU_RELAY_PID=$!
  disown || true
fi

exec ros2 run ros_gz_bridge parameter_bridge \
  "${_bridge_specs[@]}" \
  --ros-args --log-level "${WAREHOUSE_GAZEBO_BRIDGE_LOG_LEVEL}"
