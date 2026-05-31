#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export ROS_DISTRO="${ROS_DISTRO:-jazzy}"
export ROS_WS_SETUP="${ROS_WS_SETUP:-warehouse_ros2_ws/install/setup.bash}"
export WAREHOUSE_GAZEBO_SIM="${WAREHOUSE_GAZEBO_SIM:-1}"
export WAREHOUSE_TOPIC_PROFILE="${WAREHOUSE_TOPIC_PROFILE:-gazebo}"
export WAREHOUSE_ROS_PROFILE="${WAREHOUSE_ROS_PROFILE:-gazebo}"
export WAREHOUSE_ROS_BRIDGE_URL="${WAREHOUSE_ROS_BRIDGE_URL:-http://127.0.0.1:8088}"
export WAREHOUSE_ROS_WS_URL="${WAREHOUSE_ROS_WS_URL:-ws://127.0.0.1:9090}"

# Health: cheap /health, cached deeper probe in background.
export WAREHOUSE_HEALTH_BACKGROUND_PROBE="${WAREHOUSE_HEALTH_BACKGROUND_PROBE:-1}"
export WAREHOUSE_HEALTH_REFRESH_INTERVAL_S="${WAREHOUSE_HEALTH_REFRESH_INTERVAL_S:-15}"
export WAREHOUSE_HEALTH_DEEP_STALE_S="${WAREHOUSE_HEALTH_DEEP_STALE_S:-60}"
export WAREHOUSE_HEALTH_STARTUP_DELAY_S="${WAREHOUSE_HEALTH_STARTUP_DELAY_S:-1.0}"
export WAREHOUSE_TOPIC_HEALTH_MODE="${WAREHOUSE_TOPIC_HEALTH_MODE:-presence}"
export WAREHOUSE_GAZEBO_PROBE_ON_HEALTH="${WAREHOUSE_GAZEBO_PROBE_ON_HEALTH:-0}"
export WAREHOUSE_TF_PROBE_ON_HEALTH="${WAREHOUSE_TF_PROBE_ON_HEALTH:-0}"

# ROS graph calls must be short; long calls were blocking the backend/UI.
export WAREHOUSE_ROS_TOPIC_LIST_BG_TIMEOUT_S="${WAREHOUSE_ROS_TOPIC_LIST_BG_TIMEOUT_S:-3.5}"
export WAREHOUSE_ROS_TOPIC_LIST_BG_ATTEMPTS="${WAREHOUSE_ROS_TOPIC_LIST_BG_ATTEMPTS:-2}"
export WAREHOUSE_ROS_TOPIC_LIST_TIMEOUT_S="${WAREHOUSE_ROS_TOPIC_LIST_TIMEOUT_S:-3.0}"
export WAREHOUSE_ROS_TOPIC_LIST_ATTEMPTS="${WAREHOUSE_ROS_TOPIC_LIST_ATTEMPTS:-2}"

# Expensive probes stay opt-in.
export WAREHOUSE_TOPIC_INFO_TIMEOUT_S="${WAREHOUSE_TOPIC_INFO_TIMEOUT_S:-1.0}"
export WAREHOUSE_TOPIC_HZ_TIMEOUT_S="${WAREHOUSE_TOPIC_HZ_TIMEOUT_S:-1.0}"
export WAREHOUSE_TOPIC_HZ_WINDOW="${WAREHOUSE_TOPIC_HZ_WINDOW:-2}"
export WAREHOUSE_TOPIC_PROBE_WORKERS="${WAREHOUSE_TOPIC_PROBE_WORKERS:-4}"
export WAREHOUSE_TOPIC_ECHO_PROBE="${WAREHOUSE_TOPIC_ECHO_PROBE:-0}"
export WAREHOUSE_TOPIC_RESOLVE_WITH_PROBES="${WAREHOUSE_TOPIC_RESOLVE_WITH_PROBES:-0}"
export WAREHOUSE_TOPIC_REQUIRE_HZ="${WAREHOUSE_TOPIC_REQUIRE_HZ:-0}"

# Stop should be fast. Enable only when you explicitly want a fallback rosbag.
export WAREHOUSE_RECORD_SNAPSHOT_ON_STOP="${WAREHOUSE_RECORD_SNAPSHOT_ON_STOP:-0}"
export WAREHOUSE_RECORD_SNAPSHOT_DURATION_S="${WAREHOUSE_RECORD_SNAPSHOT_DURATION_S:-2}"

export WAREHOUSE_CAPTURE_ROOT="${WAREHOUSE_CAPTURE_ROOT:-${PWD}/data/warehouse_ros}"
export WAREHOUSE_ROS_CAPTURE_ROOT="${WAREHOUSE_ROS_CAPTURE_ROOT:-${WAREHOUSE_CAPTURE_ROOT}}"
mkdir -p "${WAREHOUSE_CAPTURE_ROOT}"

export AMENT_TRACE_SETUP_FILES="${AMENT_TRACE_SETUP_FILES:-}"

set +u
source "/opt/ros/${ROS_DISTRO}/setup.bash"
if [ -f "${ROS_WS_SETUP}" ]; then
  source "${ROS_WS_SETUP}"
fi
set -u

export PYTHONPATH="${PWD}/warehouse_ros2_ws/src/warehouse_mapping_bridge:${PYTHONPATH:-}"

BRIDGE_PYTHON="${WAREHOUSE_BRIDGE_PYTHON:-${PWD}/.venv/bin/python}"
if [ ! -x "${BRIDGE_PYTHON}" ]; then
  BRIDGE_PYTHON="$(command -v python3)"
fi

echo "[warehouse_bridge] start app_python=$(${BRIDGE_PYTHON} -V 2>&1) python_path=${BRIDGE_PYTHON} profile=${WAREHOUSE_TOPIC_PROFILE} capture_root=${WAREHOUSE_CAPTURE_ROOT} bridge=${WAREHOUSE_ROS_BRIDGE_URL} ws=${WAREHOUSE_ROS_WS_URL} ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"

_wait_ros_core_topics() {
  local wait_s="${WAREHOUSE_BRIDGE_SENSOR_WAIT_S:-120}"
  local topics=(
    "${WAREHOUSE_RGB_TOPIC:-/warehouse/front/rgbd/image}"
    "${WAREHOUSE_DEPTH_TOPIC:-/warehouse/front/rgbd/depth_image}"
    "${WAREHOUSE_IMU_TOPIC:-/imu}"
    "${WAREHOUSE_ODOMETRY_TOPIC:-/warehouse/drone/odometry}"
  )
  local deadline=$((SECONDS + wait_s))
  echo "[warehouse_bridge] waiting for core ROS topics (up to ${wait_s}s)..."
  while (( SECONDS < deadline )); do
    local missing=()
    for topic in "${topics[@]}"; do
      if ! timeout 3 ros2 topic info "${topic}" >/dev/null 2>&1; then
        missing+=("${topic}")
      fi
    done
    if ((${#missing[@]} == 0)); then
      echo "[warehouse_bridge] core ROS topics listed: ${topics[*]}"
      return 0
    fi
    echo "[warehouse_bridge] waiting for: ${missing[*]}"
    sleep 2
  done
  echo "[warehouse_bridge] WARN: starting without all core ROS topics (Gazebo may still be idle)" >&2
}

if [ "${WAREHOUSE_BRIDGE_WAIT_FOR_TOPICS:-1}" = "1" ]; then
  _wait_ros_core_topics
fi

exec "${BRIDGE_PYTHON}" -m warehouse_mapping_bridge.bridge_service