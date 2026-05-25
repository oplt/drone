#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <mission_id> [seconds_to_wait]"
  exit 1
fi

MISSION_ID="$1"
WAIT_SECONDS="${2:-20}"
API_BASE_URL="${IRRIGATION_API_BASE_URL:-http://127.0.0.1:8000}"
ROS_CACHE_DIR="${IRRIGATION_ROS2_CACHE_DIR:-backend/storage/irrigation_ros2}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
}
trap cleanup EXIT
PIDS=()

if ! command -v gz >/dev/null 2>&1; then
  echo "gz CLI not found"
  exit 1
fi

if ! command -v ros2 >/dev/null 2>&1; then
  echo "ros2 CLI not found"
  exit 1
fi

GAZEBO_TOPIC="$("$PYTHON_BIN" - <<'PY'
from backend.entrypoints.ros2.common import choose_gazebo_camera_topic
topic = choose_gazebo_camera_topic()
print(topic or "")
PY
)"

if [[ -z "$GAZEBO_TOPIC" ]]; then
  echo "No Gazebo camera image topic discovered via 'gz topic -l'"
  exit 1
fi

echo "Discovered Gazebo camera topic: $GAZEBO_TOPIC"
echo "Bridging Gazebo image topic into ROS 2"

ros2 run ros_gz_bridge parameter_bridge "${GAZEBO_TOPIC}@sensor_msgs/msg/Image[gz.msgs.Image" >/tmp/irrigation_ros_gz_bridge.log 2>&1 &
PIDS+=($!)

export IRRIGATION_API_BASE_URL="$API_BASE_URL"
export IRRIGATION_ROS_CAMERA_INPUT_TOPIC="$GAZEBO_TOPIC"
export IRRIGATION_ROS2_CACHE_DIR="$ROS_CACHE_DIR"

"$PYTHON_BIN" -m backend.entrypoints.ros2.telemetry_state_node >/tmp/irrigation_telemetry_state_node.log 2>&1 &
PIDS+=($!)
"$PYTHON_BIN" -m backend.entrypoints.ros2.camera_bridge_node >/tmp/irrigation_camera_bridge_node.log 2>&1 &
PIDS+=($!)
"$PYTHON_BIN" -m backend.entrypoints.ros2.capture_sync_node >/tmp/irrigation_capture_sync_node.log 2>&1 &
PIDS+=($!)

echo "Waiting ${WAIT_SECONDS}s for captures to upload..."
sleep "$WAIT_SECONDS"

SUMMARY_URL="${API_BASE_URL%/}/irrigation/missions/${MISSION_ID}/summary"
AUTH_HEADER=()
if [[ -n "${IRRIGATION_API_TOKEN:-}" ]]; then
  AUTH_HEADER=(-H "Authorization: Bearer ${IRRIGATION_API_TOKEN}")
fi

SUMMARY_JSON="$(curl -sf "${AUTH_HEADER[@]}" "$SUMMARY_URL")"
CAPTURE_COUNT="$("$PYTHON_BIN" - <<'PY' "$SUMMARY_JSON"
import json, sys
payload = json.loads(sys.argv[1])
print(int(payload.get("capture_count") or 0))
PY
)"

echo "Mission summary: $SUMMARY_JSON"
if [[ "$CAPTURE_COUNT" -lt 1 ]]; then
  echo "Smoke test failed: no captures uploaded"
  exit 2
fi

echo "Smoke test passed: ${CAPTURE_COUNT} captures uploaded for mission ${MISSION_ID}"
