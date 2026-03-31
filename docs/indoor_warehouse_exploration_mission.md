# Indoor Warehouse Exploration Mission

## Purpose

`UnknownWarehouseExplorationMission` adds a new indoor mission type for warehouse mapping and exploration when there is no prior warehouse geometry and no GPS/GSM dependency.

It is designed for LiDAR SLAM based operation from a known dock:

- launch from dock
- bootstrap a local map near the dock
- build an initial navigable skeleton
- select and visit frontiers over known free space
- preserve a safe route back to dock at every decision point
- run a separate precision docking phase before landing

The mission lives in [backend/flight/missions/warehouse_exploration_mission.py](/home/polat/Desktop/Projects/drone_app/backend/flight/missions/warehouse_exploration_mission.py).

## Architecture

The implementation is split into a small indoor domain package under [backend/flight/indoor](/home/polat/Desktop/Projects/drone_app/backend/flight/indoor):

- [backend/flight/indoor/models.py](/home/polat/Desktop/Projects/drone_app/backend/flight/indoor/models.py)
  Local poses, dock poses, occupancy grid, frontiers, SLAM health, docking targets, and return margin models.
- [backend/flight/indoor/frontier.py](/home/polat/Desktop/Projects/drone_app/backend/flight/indoor/frontier.py)
  Frontier extraction, scoring, and selection.
- [backend/flight/indoor/return_margin.py](/home/polat/Desktop/Projects/drone_app/backend/flight/indoor/return_margin.py)
  Battery/path/time gating for continue-vs-return decisions.
- [backend/flight/indoor/skeleton_graph.py](/home/polat/Desktop/Projects/drone_app/backend/flight/indoor/skeleton_graph.py)
  Confirmed navigation graph, initial skeleton seeding, and loop-closure scheduling.
- [backend/flight/indoor/slam.py](/home/polat/Desktop/Projects/drone_app/backend/flight/indoor/slam.py)
  SLAM provider protocol and a simulation-friendly provider.
- [backend/flight/indoor/local_navigation.py](/home/polat/Desktop/Projects/drone_app/backend/flight/indoor/local_navigation.py)
  Local navigation adapter protocol plus drone and simulated adapters.
- [backend/flight/indoor/docking.py](/home/polat/Desktop/Projects/drone_app/backend/flight/indoor/docking.py)
  Docking controller protocol and the default precision docking controller.

The mission still uses the existing orchestrator contract:

- `get_waypoints()`
- `execute(self, orch, alt=...)`
- `orch.run_mission(..., flight_fn=...)`

No indoor navigation logic uses GPS waypoints. `get_waypoints()` returns an empty list and the only GPS-shaped value is an explicit placeholder anchor used only for the existing flight-record schema.

## Frames

The indoor flow uses explicit local frames:

- `body`
  Sensor/controller local frame.
- `odom`
  Low-level control frame for setpoints.
- `map`
  Planner frame used by occupancy, frontier, and return planning.
- `dock`
  Final precision docking frame anchored at the dock.

The mission plans in `map`, the navigation adapter sends setpoints in `odom`, and the docking controller finishes in `dock`.

## Exploration Loop

High-level states are defined in [backend/flight/indoor/enums.py](/home/polat/Desktop/Projects/drone_app/backend/flight/indoor/enums.py):

- `IDLE_AT_DOCK`
- `INDOOR_PREFLIGHT`
- `TAKEOFF_SAFE_BUBBLE`
- `BOOTSTRAP_LOCAL_MAP`
- `BUILD_SKELETON`
- `SELECT_FRONTIER`
- `TRANSIT_TO_FRONTIER`
- `MAP_FRONTIER_REGION`
- `FORCE_LOOP_CLOSURE`
- `CHECK_RETURN_MARGIN`
- `RETURN_TO_DOCK`
- `PRECISION_DOCK`
- `LAND_AND_FINALIZE`
- degraded states for relocalization, backtracking, safe land, and abort

The runtime loop is:

1. Initialize dock reference and create the dock graph node.
2. Take off vertically inside a configurable safe bubble.
3. Run a short bootstrap scan around the dock to seed LiDAR SLAM.
4. Seed a local skeleton graph from observed free space near the dock.
5. Extract frontiers from the current occupancy snapshot.
6. Score frontiers using information gain, path cost, clearance, localization confidence, drift penalty, return-graph distance, battery cost, and skeleton bias.
7. Reject frontiers that do not preserve a safe return path and reserve.
8. Transit only through known free cells with clearance.
9. Periodically force loop closure by revisiting confirmed graph nodes.
10. Return to dock when no viable frontier remains or the return margin gets tight.

## Return Logic

Return gating uses [backend/flight/indoor/return_margin.py](/home/polat/Desktop/Projects/drone_app/backend/flight/indoor/return_margin.py).

At each decision point the mission estimates:

- outbound travel cost
- frontier mapping buffer cost
- return-to-dock cost
- projected remaining battery percentage
- time budget against `max_mission_time_s`

If a frontier cannot be explored while preserving the configured return reserve, it is rejected. If the current pose cannot preserve an emergency reserve for return, the mission triggers a safe land.

Return-to-dock planning prefers a path through the current occupancy map and falls back to the confirmed skeleton graph if needed.

## Precision Docking

Docking is separated from exploration:

- return path ends at a dock approach pose
- `PrecisionDockingController` computes the final target in the `dock` frame
- final approach is slower than exploration transit
- docking can retry once after a bounded search near the dock

This keeps the endgame controller isolated from frontier exploration logic.

## Indoor Preflight

`indoor_exploration` uses a dedicated indoor preflight branch:

- [backend/flight/preflight_check/indoor_checks.py](/home/polat/Desktop/Projects/drone_app/backend/flight/preflight_check/indoor_checks.py)
- [backend/flight/preflight_check/profiles/indoor_warehouse.py](/home/polat/Desktop/Projects/drone_app/backend/flight/preflight_check/profiles/indoor_warehouse.py)

The indoor profile checks:

- connectivity and heartbeat freshness
- armability and estimator readiness
- local position availability
- LiDAR health
- rangefinder / altitude source health
- proximity source health
- SLAM/localization pipeline readiness
- dock reference availability
- takeoff bubble clearance
- indoor mission parameter sanity
- reserve and localization threshold consistency

It does not require GPS fix, HDOP, satellite count, or home-distance assumptions.

Outdoor missions still use the existing GPS-oriented base preflight path.

## Extension Points

The new mission is deliberately vendor-neutral. Real hardware integration should plug into these protocols:

- `SLAMProvider`
  Replace the simulated provider with a ROS2, VIO, LiDAR SLAM, or vendor SDK adapter.
- `LocalNavigationAdapter`
  Map `LocalPose` paths into the flight controller’s indoor/local control API.
- `DockingController`
  Add fiducial, short-range beacon, UWB, or vision-based docking logic.

Recommended next integration steps:

- map `SLAMProvider.to_control_frame()` to a real `map -> odom` transform source
- surface `slam_ready`, `localization_confidence`, `dock_reference_ready`, and related telemetry from the actual vehicle stack
- persist final indoor map snapshots and graph outputs into warehouse storage the same way warehouse scan artifacts are persisted today
- replace the default docking retry sweep with hardware-specific fiducial reacquisition
