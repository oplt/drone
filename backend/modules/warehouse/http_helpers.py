from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.organizations.service import can_access_org_scope
from backend.modules.warehouse.http_models import (
    WarehouseDockOut,
    WarehouseLocalPose,
    WarehouseMapOut,
    WarehouseScannedMapAssetOut,
    WarehouseScannedMapQualityOut,
    WarehouseSensorRigOut,
)
from backend.modules.warehouse.http_access import repo
from backend.modules.warehouse.models import (
    WarehouseAsset,
    WarehouseDockStation,
    WarehouseInspectionMission,
    WarehouseInspectionResult,
    WarehouseMap,
    WarehouseMappingJob,
    WarehouseModel,
    WarehouseScanTarget,
    WarehouseSensorRig,
)
from backend.modules.warehouse.schemas import (
    WarehouseInspectionMissionRead,
    WarehouseInspectionResultRead,
    WarehouseScanTargetRead,
)

def map_out(row: WarehouseMap) -> WarehouseMapOut:
    return WarehouseMapOut(
        id=int(row.id),
        name=row.name,
        area_m2=row.area_m2,
        created_at=row.created_at,
        polygon_local_m=repo.polygon_from_local(row),
    )


def pose(payload: dict[str, Any]) -> WarehouseLocalPose:
    return WarehouseLocalPose.model_validate(payload or {})


def dock_out(row: WarehouseDockStation) -> WarehouseDockOut:
    meta = row.meta_data if isinstance(row.meta_data, dict) else {}
    return WarehouseDockOut(
        id=int(row.id),
        name=row.name,
        marker_id=row.marker_id,
        marker_family=meta.get("marker_family"),
        marker_size_m=meta.get("marker_size_m"),
        marker_pose_covariance=list(meta.get("marker_pose_covariance") or []),
        marker_visible=meta.get("marker_visible"),
        last_observed_at=meta.get("last_observed_at"),
        charger_type=row.charger_type,
        pose=_pose(row.pose_local_json),
        entry_pose=_pose(row.entry_pose_local_json),
        exit_pose=_pose(row.exit_pose_local_json),
        active=bool(row.active),
        created_at=row.created_at,
    )


def scan_target_out(row: WarehouseScanTarget) -> WarehouseScanTargetRead:
    return WarehouseScanTargetRead.model_validate(
        {
            "id": int(row.id),
            "warehouse_map_id": int(row.warehouse_map_id),
            "reference_model_id": row.reference_model_id,
            "dock_station_id": row.dock_station_id,
            "aisle_code": row.aisle_code,
            "rack_code": row.rack_code,
            "shelf_level": row.shelf_level,
            "bin_code": row.bin_code,
            "sku": row.sku,
            "barcode": row.barcode,
            "product_name": row.product_name,
            "target_point_local_json": row.target_point_local_json,
            "scan_pose_local_json": row.scan_pose_local_json,
            "shelf_normal_local_json": row.shelf_normal_local_json,
            "standoff_m": row.standoff_m,
            "hover_time_s": row.hover_time_s,
            "scan_timeout_s": row.scan_timeout_s,
            "priority": row.priority,
            "active": row.active,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def inspection_mission_out(row: WarehouseInspectionMission) -> WarehouseInspectionMissionRead:
    plan = row.plan_json if isinstance(row.plan_json, dict) else {}
    return WarehouseInspectionMissionRead.model_validate(
        {
            "id": int(row.id),
            "warehouse_map_id": int(row.warehouse_map_id),
            "name": row.name,
            "status": row.status,
            "scan_mode": row.scan_mode,
            "return_to_dock": row.return_to_dock,
            "target_ids": list(row.target_ids_json or []),
            "waypoints": list(plan.get("waypoints") or []),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def inspection_result_out(row: WarehouseInspectionResult) -> WarehouseInspectionResultRead:
    return WarehouseInspectionResultRead.model_validate(
        {
            "id": int(row.id),
            "mission_id": int(row.mission_id),
            "target_id": int(row.target_id),
            "status": row.status,
            "expected_barcode": row.expected_barcode,
            "detected_barcode": row.detected_barcode,
            "confidence": row.confidence,
            "image_asset_id": row.image_asset_id,
            "video_asset_id": row.video_asset_id,
            "drone_pose_local_json": row.drone_pose_local_json,
            "error_message": row.error_message,
            "scanned_at": row.scanned_at,
        }
    )


async def get_scan_target_or_404(
    db: AsyncSession,
    *,
    warehouse_map_id: int,
    target_id: int,
    active_only: bool = False,
) -> WarehouseScanTarget:
    clauses = [
        WarehouseScanTarget.id == target_id,
        WarehouseScanTarget.warehouse_map_id == warehouse_map_id,
    ]
    if active_only:
        clauses.append(WarehouseScanTarget.active.is_(True))
    target = (await db.execute(select(WarehouseScanTarget).where(*clauses))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Warehouse scan target not found")
    return target


def sensor_rig_out(row: WarehouseSensorRig) -> WarehouseSensorRigOut:
    return WarehouseSensorRigOut.model_validate(
        {
            "id": int(row.id),
            "name": row.name,
            "camera_model": row.camera_model,
            "stereo_baseline_m": row.stereo_baseline_m,
            "intrinsics_url": row.intrinsics_url,
            "extrinsics_url": row.extrinsics_url,
            "imu_transform_json": row.imu_transform_json or {},
            "firmware_version": row.firmware_version,
            "isaac_ros_version": row.isaac_ros_version,
            "calibration_status": row.calibration_status,
            "calibration_hash": row.calibration_hash,
            "calibration_meta": row.calibration_meta or {},
            "active": bool(row.active),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def asset_out(row: WarehouseAsset) -> WarehouseScannedMapAssetOut:
    return WarehouseScannedMapAssetOut(
        id=int(row.id),
        type=row.type,
        url=row.url,
        created_at=row.created_at,
        meta_data=row.meta_data or {},
    )


def source(job: WarehouseMappingJob, warehouse_map: WarehouseMap) -> str:
    meta = warehouse_map.meta_data if isinstance(warehouse_map.meta_data, dict) else {}
    if meta.get("source") == "simulation" or job.processor == "simulation":
        return "simulation"
    if job.processor == "warehouse_manual_mapping":
        return "real_flight"
    return str(job.processor or "warehouse_scan")


def quality(
    job: WarehouseMappingJob,
    warehouse_map: WarehouseMap,
    assets: list[WarehouseAsset],
) -> WarehouseScannedMapQualityOut:
    report_asset = next((a for a in assets if a.type.upper() == "QUALITY_REPORT"), None)
    report = dict(report_asset.meta_data or {}) if report_asset else {}
    quality = report.get("quality_score")
    coverage = report.get("coverage_percent")
    drift = report.get("drift_estimate_m")
    return WarehouseScannedMapQualityOut(
        job_id=int(job.id),
        quality_score=float(quality) if isinstance(quality, int | float) else None,
        coverage_percent=float(coverage) if isinstance(coverage, int | float) else None,
        drift_estimate_m=float(drift) if isinstance(drift, int | float) else None,
        source=_source(job, warehouse_map),
        report=report,
    )


async def get_scanned_map_row_or_404(
    db: AsyncSession,
    *,
    job_id: int,
    user: Any,
) -> tuple[WarehouseMappingJob, WarehouseMap, WarehouseModel]:
    scope = (
        or_(WarehouseMap.owner_id == int(user.id), WarehouseMap.org_id == user.org_id)
        if can_access_org_scope(user) and user.org_id is not None
        else WarehouseMap.owner_id == int(user.id)
    )
    # Use a direct indexed lookup instead of listing the latest 200 maps and scanning in Python.
    row = (
        await db.execute(
            select(WarehouseMappingJob, WarehouseMap, WarehouseModel)
            .join(WarehouseMap, WarehouseMappingJob.warehouse_map_id == WarehouseMap.id)
            .join(WarehouseModel, WarehouseMappingJob.model_id == WarehouseModel.id)
            .where(WarehouseMappingJob.id == int(job_id), scope)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Warehouse scanned map not found")
    return row[0], row[1], row[2]
