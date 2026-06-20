from backend.modules.warehouse.routers.docks import router as docks_router
from backend.modules.warehouse.routers.live_map import router as live_map_router
from backend.modules.warehouse.routers.maps import router as maps_router
from backend.modules.warehouse.routers.operations import router as operations_router
from backend.modules.warehouse.routers.preflight import router as preflight_router
from backend.modules.warehouse.routers.scan_targets import router as scan_targets_router
from backend.modules.warehouse.routers.scanned_maps import router as scanned_maps_router
from backend.modules.warehouse.routers.sensor_rigs import router as sensor_rigs_router
from backend.modules.warehouse.routers.settings import router as settings_router
from backend.modules.warehouse.routers.structure import router as structure_router

__all__ = [
    "docks_router",
    "live_map_router",
    "maps_router",
    "operations_router",
    "preflight_router",
    "scan_targets_router",
    "scanned_maps_router",
    "sensor_rigs_router",
    "settings_router",
    "structure_router",
]
