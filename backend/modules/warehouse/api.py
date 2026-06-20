"""Warehouse HTTP API — aggregates domain sub-routers under /warehouse."""

from __future__ import annotations

from fastapi import APIRouter

from backend.modules.warehouse.flight_api import router as warehouse_flight_router
from backend.modules.warehouse.http_models import (
    WarehouseCommandOut,
    WarehouseExplorationProfileOut,
    WarehouseExplorationStartIn,
    WarehouseLocalPose,
    WarehouseMapCreateIn,
    WarehouseMapOut,
    WarehouseMappingStackStatusOut,
    WarehouseMissionLaunchOut,
    WarehouseMissionStartIn,
    WarehousePreflightOut,
    WarehousePreflightRefreshOut,
    WarehouseScannedMapCompareIn,
    WarehouseScannedMapCompareOut,
    WarehouseScannedMapOut,
    WarehouseScannedMapQualityOut,
    WarehouseSensorRigCalibrationIn,
    WarehouseSensorRigCreateIn,
    WarehouseSensorRigHealthOut,
    WarehouseSensorRigOut,
)
from backend.modules.warehouse.routers import (
    docks_router,
    live_map_router,
    maps_router,
    operations_router,
    preflight_router,
    scan_targets_router,
    scanned_maps_router,
    sensor_rigs_router,
    settings_router,
    structure_router,
)
from backend.modules.warehouse.routers.live_map import (
    WAREHOUSE_LIVE_MAP_BATCH_MAX_CHUNKS,
    WarehouseLiveMapChunkBatchIn,
    WarehouseLiveMapChunkUploadOut,
    WarehouseLiveMapPublishOut,
)
from backend.modules.warehouse.ros_bridge_runtime import ensure_ros_bridge_running, ros2_workspace

router = APIRouter(prefix="/warehouse", tags=["warehouse"])
router.include_router(maps_router)
router.include_router(structure_router)
router.include_router(scan_targets_router)
router.include_router(docks_router)
router.include_router(sensor_rigs_router)
router.include_router(settings_router)
router.include_router(scanned_maps_router)
router.include_router(preflight_router)
router.include_router(operations_router)
router.include_router(live_map_router)
router.include_router(warehouse_flight_router)

__all__ = [
    "router",
    "WarehouseCommandOut",
    "WarehouseExplorationProfileOut",
    "WarehouseExplorationStartIn",
    "WarehouseLocalPose",
    "WarehouseLiveMapChunkBatchIn",
    "WarehouseLiveMapChunkUploadOut",
    "WarehouseLiveMapPublishOut",
    "WarehouseMapCreateIn",
    "WarehouseMapOut",
    "WarehouseMappingStackStatusOut",
    "WarehouseMissionLaunchOut",
    "WarehouseMissionStartIn",
    "WarehousePreflightOut",
    "WarehousePreflightRefreshOut",
    "WarehouseScannedMapCompareIn",
    "WarehouseScannedMapCompareOut",
    "WarehouseScannedMapOut",
    "WarehouseScannedMapQualityOut",
    "WarehouseSensorRigCalibrationIn",
    "WarehouseSensorRigCreateIn",
    "WarehouseSensorRigHealthOut",
    "WarehouseSensorRigOut",
    "WAREHOUSE_LIVE_MAP_BATCH_MAX_CHUNKS",
    "ensure_ros_bridge_running",
    "ros2_workspace",
]
