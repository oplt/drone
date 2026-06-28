# Warehouse Inspection Workflow

`warehouse_scan -> 3D map -> create scan targets -> warehouse_inspection -> barcode/product results`

`warehouse_scan` remains the coverage/mapping mission. `warehouse_inspection` is a separate product/barcode inspection flow that runs after a warehouse map exists.

Targets store two local metric poses:

- `target_point_local_json`: physical product, shelf, or barcode point.
- `scan_pose_local_json`: safe drone hover pose in front of that target.

The drone must navigate to `scan_pose_local_json`, then hover and trigger the scanner. It must not fly to `target_point_local_json`.

All poses use `frame_id: "warehouse_map"`. Before targets can be created or a
mission planned, create and lock a coordinate-frame revision with the measured
`warehouse_map -> odom` TF. Targets and missions pin that immutable revision;
missions using stale/unlocalized targets are rejected with HTTP 409. Mapping
chunks remain honest `odom` data and structure extraction applies the locked
transform before emitting `warehouse_map` targets.

MVP extension points:

- ESDF/occupancy clearance validation before mission start.
- Real barcode scanner implementation behind `WarehouseScanner`.
- Persistent map-to-odom localization for starts from arbitrary poses.
