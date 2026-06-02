# Jetson ROS 2 Warehouse Mapping Workspace

Deploy this workspace on the Jetson companion computer. It exposes the HTTP
bridge consumed by the backend `WarehousePerceptionPort` and launches the
camera/IMU/Isaac ROS mapping graph.

## Build

```bash
cd warehouse_ros2_ws
colcon build --symlink-install
source install/setup.bash
colcon test --packages-select warehouse_mapping_bridge
```

## Run Bridge

```bash
export WAREHOUSE_ROS_CAPTURE_ROOT=/backend/storage/warehouse_ros
export WAREHOUSE_ROS_PROFILE=isaac_ros_nvblox_stereo
export WAREHOUSE_ROS_AUTOLAUNCH=1
python3 -m warehouse_mapping_bridge.bridge_service
```

Backend should point `WAREHOUSE_ROS_BRIDGE_URL` at this service, for example:

```bash
WAREHOUSE_ROS_BRIDGE_URL=http://jetson.local:8088
WAREHOUSE_ROS_WS_URL=ws://jetson.local:9090
```

## Isaac Commands

Default launch uses `warehouse_mapping_bridge/launch/isaac_warehouse_mapping.launch.py`.
Override each subsystem with env vars when your exact Isaac ROS package names or
camera drivers differ:

- `WAREHOUSE_CAMERA_LAUNCH_CMD`
- `WAREHOUSE_IMU_LAUNCH_CMD`
- `WAREHOUSE_IMAGE_PIPELINE_LAUNCH_CMD`
- `WAREHOUSE_VISUAL_SLAM_LAUNCH_CMD`
- `WAREHOUSE_DEPTH_LAUNCH_CMD`
- `WAREHOUSE_NVBLOX_LAUNCH_CMD`

Each command is shell-like, for example:

```bash
WAREHOUSE_VISUAL_SLAM_LAUNCH_CMD="ros2 launch isaac_ros_visual_slam isaac_ros_visual_slam_realsense.launch.py"
```

Set `WAREHOUSE_ALLOW_PARTIAL_ISAAC_LAUNCH=1` only when you intentionally want
to start bridge helper nodes without the full camera/SLAM/nvblox stack.
