# Isaac Sim Warehouse Scenario

Stage 12 scaffold for simulation-first warehouse mapping.

Run shape:
- Build or load a warehouse digital twin in Isaac Sim.
- Attach the drone sensor profile from `drone_sensor_profile.json`.
- Export a ROS bag with stereo, IMU, TF, odometry, depth, and nvblox topics.
- Use backend `/warehouse/simulation/captures` to enqueue the same mapping worker path used by real flights.

Expected capture bundle:
- `warehouse_mapping_manifest.json`
- `quality_report.json`
- one of `tileset.json`, `.glb`, `.ply`, `.pcd`, `.mcap`, `.db3`, `.bag`

