from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

WAREHOUSE_MAP_FRAME = "warehouse_map"
ODOM_FRAME = "odom"
BASE_FRAME = "base_link"
BASE_FRD_FRAME = "base_link_frd"
LIDAR_FRAME = "lidar_link"
CAMERA_FRAME = "camera_link"
CAMERA_OPTICAL_FRAME = "camera_optical_frame"
RGBD_FRAME = "rgbd_link"
IMU_FRAME = "imu_link"
GIMBAL_FRAME = "gimbal_link"
DOCK_FRAME = "dock"

FrameRole = Literal["world", "motion", "body", "sensor", "semantic"]
PublisherKind = Literal["localization", "odometry", "calibration", "joint_state", "optional"]


class WarehouseFrameDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    frame_id: str
    parent_frame_id: str | None
    role: FrameRole
    publisher: PublisherKind
    required: bool = True
    persistent_geometry: bool = False
    units: Literal["m"] = "m"
    axis_convention: str
    handedness: Literal["right"] = "right"


FRAME_DEFINITIONS = (
    WarehouseFrameDefinition(
        frame_id=WAREHOUSE_MAP_FRAME,
        parent_frame_id=None,
        role="world",
        publisher="localization",
        persistent_geometry=True,
        axis_convention="ENU: x=warehouse_axis,y=left,z=up",
    ),
    WarehouseFrameDefinition(
        frame_id=ODOM_FRAME,
        parent_frame_id=WAREHOUSE_MAP_FRAME,
        role="motion",
        publisher="localization",
        axis_convention="ENU continuous local motion frame",
    ),
    WarehouseFrameDefinition(
        frame_id=BASE_FRAME,
        parent_frame_id=ODOM_FRAME,
        role="body",
        publisher="odometry",
        axis_convention="REP-103: x=forward,y=left,z=up",
    ),
    WarehouseFrameDefinition(
        frame_id=LIDAR_FRAME,
        parent_frame_id=BASE_FRAME,
        role="sensor",
        publisher="calibration",
        axis_convention="REP-103 sensor frame",
    ),
    WarehouseFrameDefinition(
        frame_id=CAMERA_FRAME,
        parent_frame_id=BASE_FRAME,
        role="sensor",
        publisher="calibration",
        axis_convention="REP-103 camera body frame",
    ),
    WarehouseFrameDefinition(
        frame_id=CAMERA_OPTICAL_FRAME,
        parent_frame_id=CAMERA_FRAME,
        role="sensor",
        publisher="calibration",
        axis_convention="REP-103 optical: z=forward,x=right,y=down",
    ),
    WarehouseFrameDefinition(
        frame_id=RGBD_FRAME,
        parent_frame_id=BASE_FRAME,
        role="sensor",
        publisher="calibration",
        axis_convention="REP-103 sensor frame",
    ),
    WarehouseFrameDefinition(
        frame_id=IMU_FRAME,
        parent_frame_id=BASE_FRAME,
        role="sensor",
        publisher="calibration",
        axis_convention="REP-103 sensor frame",
    ),
    WarehouseFrameDefinition(
        frame_id=GIMBAL_FRAME,
        parent_frame_id=BASE_FRAME,
        role="sensor",
        publisher="joint_state",
        axis_convention="REP-103 articulated sensor mount",
    ),
    WarehouseFrameDefinition(
        frame_id=DOCK_FRAME,
        parent_frame_id=WAREHOUSE_MAP_FRAME,
        role="semantic",
        publisher="optional",
        required=False,
        persistent_geometry=True,
        axis_convention="warehouse_map-aligned semantic frame",
    ),
)

REQUIRED_FRAME_EDGES = frozenset(
    (frame.parent_frame_id, frame.frame_id)
    for frame in FRAME_DEFINITIONS
    if frame.required and frame.parent_frame_id is not None
)
CALIBRATED_FRAME_EDGES = frozenset(
    (frame.parent_frame_id, frame.frame_id)
    for frame in FRAME_DEFINITIONS
    if frame.required and frame.publisher == "calibration"
)
REGISTERED_FRAME_IDS = frozenset(frame.frame_id for frame in FRAME_DEFINITIONS)


def validate_frame_tree(
    edges: list[tuple[str, str]] | set[tuple[str, str]], *, allow_optional: bool = True
) -> set[tuple[str, str]]:
    normalized = [(str(parent).strip(), str(child).strip()) for parent, child in edges]
    if len(normalized) != len(set(normalized)):
        raise ValueError("frame tree contains duplicate edges")
    children = [child for _, child in normalized]
    if len(children) != len(set(children)):
        raise ValueError("each TF child must have exactly one parent")
    edge_set = set(normalized)
    missing = REQUIRED_FRAME_EDGES - edge_set
    if missing:
        raise ValueError(f"frame tree is missing required edges: {sorted(missing)}")
    allowed = {
        (frame.parent_frame_id, frame.frame_id)
        for frame in FRAME_DEFINITIONS
        if frame.parent_frame_id is not None and (allow_optional or frame.required)
    }
    unknown = edge_set - allowed
    if unknown:
        raise ValueError(f"frame tree contains unregistered edges: {sorted(unknown)}")
    parents = {child: parent for parent, child in normalized}
    for child in children:
        seen: set[str] = set()
        current = child
        while current in parents:
            if current in seen:
                raise ValueError("frame tree contains a cycle")
            seen.add(current)
            current = parents[current]
    return edge_set


def frame_contract_payload(*, coordinate_frame: Any | None = None) -> dict[str, Any]:
    frames = [frame.model_dump() for frame in FRAME_DEFINITIONS]
    canonical = {"schema_version": 1, "frames": frames}
    checksum = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    active_revision = None
    if coordinate_frame is not None:
        active_revision = {
            "id": int(coordinate_frame.id),
            "version": int(coordinate_frame.version),
            "parent_frame_id": coordinate_frame.parent_frame_id,
            "child_frame_id": coordinate_frame.child_frame_id,
            "status": coordinate_frame.status,
            "transform": coordinate_frame.transform_json,
        }
    return {**canonical, "checksum_sha256": checksum, "active_revision": active_revision}
