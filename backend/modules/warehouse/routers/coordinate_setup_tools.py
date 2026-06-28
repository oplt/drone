from __future__ import annotations

from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.warehouse.http_access import get_map_or_404
from backend.modules.warehouse.service.floor_plane_ransac import fit_floor_plane_ransac
from backend.modules.warehouse.service.gazebo_landmark_consistency import (
    LandmarkObservation,
    LandmarkSpec,
    evaluate_landmark_consistency,
)
from backend.modules.warehouse.service.provisional_mapping import (
    begin_provisional_epoch,
    provisional_epoch_snapshot,
)
from backend.modules.warehouse.service.scan_odom_alignment import estimate_scan_odom_to_warehouse_map
from backend.modules.warehouse.service.slam_localization_monitor import slam_localization_snapshot

router = APIRouter(tags=["warehouse-coordinate-setup-tools"])


class FloorPlaneRansacIn(BaseModel):
    points_xyz: list[list[float]] = Field(..., min_length=3)
    distance_threshold_m: float = Field(default=0.05, gt=0.0, le=1.0)


class ScanOdomAlignIn(BaseModel):
    floor_plane: dict[str, Any]
    origin_warehouse_m: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0], min_length=3, max_length=3)
    yaw_flip_rad: float = 0.0


class LandmarkConsistencyIn(BaseModel):
    landmarks: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    map_to_odom: dict[str, Any]
    tolerance_m: float = Field(default=0.25, gt=0.0, le=5.0)


class ProvisionalEpochIn(BaseModel):
    epoch_id: str = Field(..., min_length=1, max_length=128)


@router.post("/maps/{warehouse_map_id}/coordinate-setup/floor-plane-ransac")
async def floor_plane_ransac(
    warehouse_map_id: int,
    payload: FloorPlaneRansacIn,
    org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    await get_map_or_404(warehouse_map_id=warehouse_map_id, user=org_user.user)
    points = np.asarray(payload.points_xyz, dtype=np.float64)
    return fit_floor_plane_ransac(
        points,
        distance_threshold_m=payload.distance_threshold_m,
    )


@router.post("/maps/{warehouse_map_id}/coordinate-setup/scan-odom-alignment")
async def scan_odom_alignment(
    warehouse_map_id: int,
    payload: ScanOdomAlignIn,
    org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    await get_map_or_404(warehouse_map_id=warehouse_map_id, user=org_user.user)
    origin = tuple(float(v) for v in payload.origin_warehouse_m[:3])
    return estimate_scan_odom_to_warehouse_map(
        floor_plane=payload.floor_plane,
        origin_warehouse_m=origin,  # type: ignore[arg-type]
        yaw_flip_rad=payload.yaw_flip_rad,
    )


@router.post("/maps/{warehouse_map_id}/coordinate-setup/landmark-consistency")
async def landmark_consistency(
    warehouse_map_id: int,
    payload: LandmarkConsistencyIn,
    org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    await get_map_or_404(warehouse_map_id=warehouse_map_id, user=org_user.user)
    landmarks = [
        LandmarkSpec(
            name=str(item["name"]),
            warehouse_x_m=float(item["warehouse_x_m"]),
            warehouse_y_m=float(item["warehouse_y_m"]),
            warehouse_z_m=float(item.get("warehouse_z_m") or 0.0),
        )
        for item in payload.landmarks
    ]
    observations = [
        LandmarkObservation(
            name=str(item["name"]),
            x_m=float(item["x_m"]),
            y_m=float(item["y_m"]),
            z_m=float(item.get("z_m") or 0.0),
        )
        for item in payload.observations
    ]
    return evaluate_landmark_consistency(
        landmarks=landmarks,
        observations=observations,
        map_to_odom=payload.map_to_odom,
        tolerance_m=payload.tolerance_m,
    )


@router.post("/maps/{warehouse_map_id}/coordinate-setup/provisional-epoch")
async def start_provisional_epoch(
    warehouse_map_id: int,
    payload: ProvisionalEpochIn,
    org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    await get_map_or_404(warehouse_map_id=warehouse_map_id, user=org_user.user)
    epoch = begin_provisional_epoch(warehouse_map_id=warehouse_map_id, epoch_id=payload.epoch_id)
    return {
        "epoch_id": epoch.epoch_id,
        "revision": epoch.revision,
        "slam_frame_id": epoch.slam_frame_id,
    }


@router.get("/maps/{warehouse_map_id}/coordinate-setup/provisional-status")
async def provisional_status(
    warehouse_map_id: int,
    org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    await get_map_or_404(warehouse_map_id=warehouse_map_id, user=org_user.user)
    snapshot = provisional_epoch_snapshot(warehouse_map_id)
    slam = slam_localization_snapshot()
    return {
        "provisional_epoch": snapshot,
        "slam_localization": slam,
    }
