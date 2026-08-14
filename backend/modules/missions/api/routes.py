from __future__ import annotations

from fastapi import APIRouter

from backend.modules.missions.api.audit_routes import router as audit_router
from backend.modules.missions.api.export_routes import router as export_router
from backend.modules.missions.api.mission_routes import router as mission_router
from backend.modules.missions.api.preflight_routes import router as preflight_router
from backend.modules.missions.api.preview_routes import router as preview_router
from backend.modules.missions.api.private_patrol_routes import router as private_patrol_router
from backend.modules.missions.api.routes_commands import router as commands_router
from backend.modules.missions.api.runtime_routes import router as runtime_router
from backend.modules.missions.service.mission_execution import execute_mission

router = APIRouter(prefix="/tasks", tags=["tasks"])
router.include_router(preview_router)
router.include_router(runtime_router)
router.include_router(commands_router)
router.include_router(preflight_router)
router.include_router(mission_router)
router.include_router(private_patrol_router)
router.include_router(audit_router)
router.include_router(export_router)

__all__ = ["router", "execute_mission"]
