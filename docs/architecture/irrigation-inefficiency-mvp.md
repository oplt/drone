# Irrigation Inefficiency MVP

## Architecture

The irrigation MVP keeps the existing mission architecture intact:

1. `FieldPage.tsx` still launches a `grid` mission through `/tasks/preflight/run` and `/tasks/missions`.
2. Mission runtime state remains anchored in `mission_runtimes`.
3. New irrigation stages attach after flight execution:
   - geotagged capture ingestion
   - stitched preview generation
   - heuristic anomaly analytics
   - dashboard visualization

## Backend flow

- `backend/api/routes/routes_irrigation.py`
  - `POST /irrigation/captures`
  - `GET /irrigation/missions/{mission_id}/captures`
  - `GET /irrigation/missions/{mission_id}/summary`
  - `POST /irrigation/missions/{mission_id}/process`
- `backend/services/irrigation/service.py`
  - mission-scoped asset storage
  - capture persistence
  - composite + analytics orchestration
- `backend/services/irrigation/compositor.py`
  - GPS/altitude/FOV-based approximate image placement
- `backend/services/irrigation/analytics.py`
  - RGB heuristic scoring for:
    - `under_irrigated`
    - `overwatered`
    - `uneven_distribution`
- `backend/services/irrigation/monitor.py`
  - background post-mission trigger for completed grid missions with captures

## ROS 2 integration

ROS 2 is explicit but intentionally narrow. The core backend stays FastAPI-first; ROS 2 handles runtime bridge duties.

Topics:

- `/camera/image_raw`
- `/drone/state`
- `/capture/geotagged_record`
- `/mission/completed`
- `/analysis/irrigation_anomalies`

Nodes:

- `backend/ros2_irrigation/camera_bridge_node.py`
  - discovers the live Gazebo camera topic or accepts `IRRIGATION_GAZEBO_CAMERA_TOPIC`
  - republishes the bridged image feed onto `/camera/image_raw`
- `backend/ros2_irrigation/telemetry_state_node.py`
  - polls backend ops/telemetry state and publishes normalized drone state
- `backend/ros2_irrigation/capture_sync_node.py`
  - nearest-timestamp sync between image frames and state samples
  - enforces `IRRIGATION_CAPTURE_INTERVAL_S`
  - persists a local ROS 2 spool copy
  - uploads mission-linked captures to `/irrigation/captures`
- `backend/ros2_irrigation/processing_trigger_node.py`
  - detects terminal mission state
  - publishes `/mission/completed`
  - triggers backend processing
  - publishes `/analysis/irrigation_anomalies`

## Environment

- `IRRIGATION_STORAGE_DIR`
- `IRRIGATION_CAPTURE_INTERVAL_S`
- `IRRIGATION_CAMERA_FOV_H_DEG`
- `IRRIGATION_CAMERA_FOV_V_DEG`
- `IRRIGATION_MONITOR_POLL_S`
- `IRRIGATION_API_BASE_URL`
- `IRRIGATION_API_TOKEN`
- `IRRIGATION_ROS2_CACHE_DIR`
- `IRRIGATION_CAPTURE_SYNC_TOLERANCE_S`
- `IRRIGATION_MISSION_POLL_S`
- `IRRIGATION_ACTIVE_MISSION_ID` (optional manual override only)

## Running locally

Backend direct processing:

```bash
python3 -m backend.scripts.run_irrigation_pipeline <mission_id> --force
```

ROS 2 bridge lane:

```bash
python3 -m backend.ros2_irrigation.telemetry_state_node
python3 -m backend.ros2_irrigation.capture_sync_node
python3 -m backend.ros2_irrigation.processing_trigger_node
```

`camera_bridge_node` is only needed when the simulation feed needs topic normalization.

Gazebo topic discovery:

- The bridge now inspects `gz topic -l` and prefers image topics containing `iris`, `camera`, and `sensor`
- Override manually with `IRRIGATION_GAZEBO_CAMERA_TOPIC=<gz_topic>`
- Override the ROS-side bridged input with `IRRIGATION_ROS_CAMERA_INPUT_TOPIC=<ros_topic>`

End-to-end smoke test:

```bash
chmod +x backend/scripts/smoke_test_irrigation_ros2.sh
backend/scripts/smoke_test_irrigation_ros2.sh <mission_id> 20
```

What it does:

- discovers the live Gazebo image topic
- launches `ros_gz_bridge parameter_bridge`
- launches telemetry, camera, and capture sync ROS 2 nodes
- derives the active mission id from backend ops health / `/drone/state`
- waits for uploads
- checks `/irrigation/missions/{mission_id}/summary` and fails if `capture_count < 1`

## MVP limitations

- Image placement is an approximate nadir-footprint composite, not a survey-grade orthomosaic.
- RGB-only heuristics infer irrigation stress; they are not agronomic truth.
- Band detection is based on spatial inconsistency and elongated clusters, not row-semantic crop modeling.
- ROS 2 nodes use JSON payloads on `std_msgs/String` for state and outputs to avoid custom message generation in the MVP.

## Upgrade path

- Replace the compositor with an orthomosaic/WebODM path when camera overlap and calibration are reliable.
- Replace heuristic analytics with a learned classifier or multispectral/thermal feature stack.
- Promote JSON topics to custom ROS 2 message definitions when the interface stabilizes.
