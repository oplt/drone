# Warehouse Live 3D Map — Developer Validation

Multi-layer live mapping uses ROS topic sources configured in
`backend/modules/warehouse/service/map_source_config.py` and streamed to the
Warehouse 3D Map page over WebSocket + chunk download APIs.

## ROS topic checks

```bash
ros2 topic info /warehouse/front/rgbd/points
ros2 topic echo /warehouse/front/rgbd/points --once
ros2 topic hz /warehouse/front/rgbd/points
ros2 topic hz /nvblox_node/color_layer
ros2 topic hz /nvblox_node/static_esdf_pointcloud
ros2 topic hz /nvblox_node/mesh
ros2 run tf2_ros tf2_echo odom base_link
ros2 run tf2_tools view_frames
```

## Backend diagnostics API

While the backend is running:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/warehouse/live-map/diagnostics | jq
```

Reports RGB-D / LiDAR / nvBlox topic publishing, TF chain warnings, RGB field
detection, and nvBlox status (`off`, `warming`, `live`, `degraded`, `error`).

## Live map layers

| Layer | ROS topic | Chunk prefix |
|-------|-----------|--------------|
| Mid360 LiDAR raw | `/warehouse/mid360/points` | `mid360_######` |
| RGB-D colored | `/warehouse/front/rgbd/points` | `rgbd_######` |
| nvBlox color | `/nvblox_node/color_layer` | `nvblox_color_######` |
| nvBlox ESDF | `/nvblox_node/static_esdf_pointcloud` | `nvblox_esdf_########` |
| nvBlox TSDF | `/nvblox_node/tsdf_layer` | `nvblox_tsdf_######` |

Binary chunk encodings:

- `xyz32_v1` — contiguous Float32 XYZ (`application/vnd.live-map.xyz32`)
- `xyzrgb32_v1` — Float32 XYZ + Uint8 RGB (`application/vnd.live-map.xyzrgb32`)

## Frontend controls

On the Warehouse 3D Map card:

- Toggle layers (RGB-D, Mid360, nvBlox color/ESDF/TSDF/mesh, drone path, grid)
- Adjust point size and per-layer point budgets
- Pause/resume live stream and clear accumulated chunks
- Switch color mode: RGB / height / distance / layer color

## Chunk retention

Frontend state and binary cache retain the **latest N chunks per layer**, not
globally by sequence. Mid360 sequence 256 and RGB-D sequence 75 no longer
compete for the same retention slot.

Saved scan replay prefers **disk snapshots** (with `.meta.json` sidecars) when
the in-memory stream is finalized, so truncated websocket history does not
replace the full on-disk chunk set.

Starting a warehouse scan calls `_restart_live_map_publisher()` which starts:

1. Odometry + health bridge (`live_map_bridge.py`)
2. Colored multi-layer bridge (`colored_pointcloud_live_map_bridge.py`)
3. Raw Mid360 bridge (`raw_pointcloud_live_map_bridge.py`)

Existing snapshot/chunk download APIs remain backward-compatible for Mid360
`.xyz32` chunks.
