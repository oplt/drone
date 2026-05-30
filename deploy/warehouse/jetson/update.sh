#!/usr/bin/env bash
set -euo pipefail

WS_DIR="${1:-/opt/warehouse_ros}"
sudo mkdir -p "${WS_DIR}/src"
sudo rsync -a jetson_ros2_ws/src/ "${WS_DIR}/src/"
sudo bash -lc "source /opt/ros/humble/setup.bash && cd '${WS_DIR}' && colcon build --symlink-install"
sudo install -m 0644 deploy/warehouse/jetson/warehouse-ros-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now warehouse-ros-bridge.service
