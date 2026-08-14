from __future__ import annotations

from fastapi import APIRouter

from backend.modules.property_patrol.api.incident_routes import router as incident_router
from backend.modules.property_patrol.api.mission_routes import router as mission_router
from backend.modules.property_patrol.api.sensor_event_routes import router as sensor_event_router
from backend.modules.property_patrol.api.site_routes import router as site_router
from backend.modules.property_patrol.api.template_routes import router as template_router

router = APIRouter(prefix="/api/property-patrol", tags=["property-patrol"])
router.include_router(site_router)
router.include_router(template_router)
router.include_router(mission_router)
router.include_router(sensor_event_router)
router.include_router(incident_router)
