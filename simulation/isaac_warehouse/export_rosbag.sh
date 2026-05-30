#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-/tmp/warehouse_sim_capture}"
mkdir -p "${OUT_DIR}"

ros2 bag record \
  --output "${OUT_DIR}/warehouse_sim" \
  /left/image_raw \
  /right/image_raw \
  /left/camera_info \
  /right/camera_info \
  /imu \
  /tf \
  /tf_static \
  /visual_slam/tracking/odometry \
  /nvblox_node/mesh \
  /nvblox_node/esdf
