# Warehouse Inspection Workflow

`warehouse_scan -> 3D map -> create scan targets -> warehouse_inspection -> barcode/product results`

`warehouse_scan` remains the coverage/mapping mission. `warehouse_inspection` is a separate product/barcode inspection flow that runs after a warehouse map exists.

Targets store two local metric poses:

- `target_point_local_json`: physical product, shelf, or barcode point.
- `scan_pose_local_json`: safe drone hover pose in front of that target.

The drone must navigate to `scan_pose_local_json`, then hover and trigger the scanner. It must not fly to `target_point_local_json`.

All v1 poses use `frame_id: "warehouse_map"`. The mission plan persists a placeholder `warehouse_map_to_odom_transform: null`; v1 assumes `warehouse_map == odom` when the drone starts from the same dock/takeoff origin. A future localization layer can fill this transform without changing target APIs.

MVP extension points:

- ESDF/occupancy clearance validation before mission start.
- Real barcode scanner implementation behind `WarehouseScanner`.
- Persistent map-to-odom localization for starts from arbitrary poses.
