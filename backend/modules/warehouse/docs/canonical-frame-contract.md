# Canonical warehouse frame contract

The runtime tree is:

`warehouse_map -> odom -> base_link`

Fixed sensor calibration owns `base_link -> lidar_link`, `base_link -> camera_link`,
`camera_link -> camera_optical_frame`, `base_link -> rgbd_link`, and
`base_link -> imu_link`. The gimbal broadcaster exclusively owns the dynamic
`base_link -> gimbal_link` edge. `warehouse_map -> dock` is optional and semantic.

Only `warehouse_map` geometry may be persisted. Live scan transport may carry
`odom` geometry until it is transformed through a locked coordinate revision.
The frontend consumes the frame contract and active revision and never relabels
coordinates.

`warehouse_bridge.launch.py` deliberately has no identity defaults for
`warehouse_map -> odom`. Supply all seven `warehouse_map_{x,y,z,qx,qy,qz,qw}`
arguments from the locked revision returned by
`GET /warehouse/maps/{id}/frame-contract`. For an intentional simulation identity,
pass zero translation, `qx=qy=qz=0`, and `qw=1` explicitly.

The calibration guard verifies fixed transforms against their checksum and then
requires every mandatory runtime frame to resolve from `warehouse_map` before its
startup deadline. Missing, duplicate, multi-parent, cyclic, or unregistered trees
are rejected by the backend contract validator.

## ENU/NED vehicle boundary

Warehouse planning and SLAM submit `EnuCoordinate` values in metres with yaw in
radians. Only `backend/infrastructure/vehicle/frame_conversion.py`, called by the
MAVLink adapter, converts ENU `(x, y, z)` to local NED
`(north=y, east=x, down=-z)` and converts yaw with `pi/2 - yaw_enu`. The inverse
telemetry conversion uses the same adapter. A locked `warehouse_map -> odom`
transform is inverted before ENU/NED conversion when commands originate in the
persistent warehouse frame. API-only angle fields retain the `_deg` suffix.

## Drift and mismatch prevention

Locked localization requires a source timestamp, explicit maximum age, finite
6x6 covariance, confidence at or above 0.5, and a SHA-256 transform checksum.
Mission planning and execution revalidate that evidence. Publishing a new locked
revision is rejected while a warehouse mission is planned or running.

Map setup records resolution in metres, enforces scale `1.0`, and optionally
checks a surveyed known distance with at most 2% relative error. ROS acquisition
bridges require an explicit source frame and a successful `tf2` lookup; colored
cloud transforms older than 500 ms are discarded. Direct transform observations
emit translation/yaw deltas and alarm metrics when configured jump limits are
exceeded.

The drift-prevention migration cannot invent evidence for legacy frames. It
backfills timestamps but uses a placeholder checksum; operators must create and
lock a newly validated revision before those maps become mission-safe.

Legacy inspection missions are non-repeatable by default because they do not pin
frame, layout, model, and path-validation revisions. The compatibility mock-run
endpoint accepts `X-Confirm-Same-Origin: true` only as an explicit operator
assertion that the vehicle uses the identical physical takeoff origin. Overrides
emit warning logs and a metric. New missions never use this escape hatch.
