#!/usr/bin/env bash
# Stop warehouse ROS/Gazebo bridge orphans only (safe patterns — no bare "relay").
set +e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 0

# Each entry is one full pgrep -f pattern ([x] avoids matching pgrep itself).
PATTERNS=(
  '[w]arehouse_bridge_stack'
  '[w]arehouse_bridge\.sh'
  '[s]tart_gazebo_sensor_bridge\.sh'
  '[r]os_gz_bridge'
  '[p]arameter_bridge'
  '[w]arehouse_topic_adapter'
  '[w]arehouse_sim_tf_broadcaster'
  '[w]arehouse_odometry_export'
  '[t]opic_tools relay'
  '[w]arehouse_imu_relay'
  '[r]osbridge_websocket'
  '[r]osapi_node'
  '[s]tart_warehouse_nvblox'
  '[n]vblox_node'
  '[w]arehouse_mapping_bridge'
)

_kill_pattern() {
  local sig="$1"
  local pattern="$2"
  local self="$$"
  local parent="$PPID"
  local pid

  while read -r pid; do
    [ -n "$pid" ] || continue

    case "$pid" in
      "$self"|"$parent"|1)
        continue
        ;;
    esac

    kill "-$sig" "$pid" 2>/dev/null || true
  done < <(pgrep -f "$pattern" 2>/dev/null || true)
}

echo "[kill_warehouse_ros_bridge] stopping bridge-related processes (SIGTERM)..."
for pattern in "${PATTERNS[@]}"; do
  _kill_pattern TERM "$pattern"
done
sleep 1
echo "[kill_warehouse_ros_bridge] SIGKILL if still running..."
for pattern in "${PATTERNS[@]}"; do
  _kill_pattern KILL "$pattern"
done

remaining="$(
  pgrep -af 'warehouse_bridge_stack|warehouse_bridge\.sh|start_gazebo_sensor_bridge\.sh|ros_gz_bridge|parameter_bridge|warehouse_topic_adapter|warehouse_sim_tf_broadcaster|warehouse_odometry_export|topic_tools relay|warehouse_imu_relay|rosbridge_websocket|rosapi_node|start_warehouse_nvblox|nvblox_node|warehouse_mapping_bridge' 2>/dev/null \
    | grep -v 'kill_warehouse_ros_bridge\.sh' \
    | grep -v 'pgrep -af' \
    || true
)"

if [ -n "$remaining" ]; then
  echo "[kill_warehouse_ros_bridge] still running:"
  echo "$remaining"
  exit 1
fi
echo "[kill_warehouse_ros_bridge] done."
exit 0
