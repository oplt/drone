#!/usr/bin/env bash
set -eo pipefail

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"

source /opt/ros/jazzy/setup.bash
source "$HOME/Desktop/Projects/drone_app/warehouse_ros2_ws/install/setup.bash"

exec ros2 run nvblox_ros nvblox_node --ros-args \
  -p num_cameras:=1 \
  -p mapping_type:=static_tsdf \
  -p use_depth:=true \
  -p use_color:=true \
  -p use_lidar:=false \
  -p use_tf_transforms:=true \
  -p global_frame:=odom \
  -p map_clearing_frame_id:=base_link \
  -p print_rates_to_console:=true \
  -r camera_0/depth/image:=/warehouse/front/rgbd/depth_image \
  -r camera_0/depth/camera_info:=/warehouse/front/rgbd/camera_info \
  -r camera_0/color/image:=/warehouse/front/rgbd/image \
  -r camera_0/color/camera_info:=/warehouse/front/rgbd/camera_info
