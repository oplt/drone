from __future__ import annotations

from fastapi import APIRouter

from backend.modules.telemetry.api.connect_routes import router as connect_router
from backend.modules.telemetry.api.health_routes import router as health_router
from backend.modules.telemetry.api.manual_control_routes import router as manual_control_router
from backend.modules.telemetry.api.runtime_routes import runtime_router
from backend.modules.telemetry.api.stream_routes import router as stream_router

router = APIRouter(prefix="/telemetry", tags=["telemetry"])
router.include_router(connect_router)
router.include_router(stream_router)
router.include_router(health_router)
router.include_router(manual_control_router)

__all__ = ["router", "runtime_router"]
