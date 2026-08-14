from __future__ import annotations

from fastapi import APIRouter

from backend.modules.mapping.api.asset_routes import router as asset_router
from backend.modules.mapping.api.field_routes import router as field_router
from backend.modules.mapping.api.job_routes import router as job_router
from backend.modules.mapping.api.upload_routes import router as upload_router

router = APIRouter(prefix="/mapping", tags=["mapping"])
router.include_router(job_router)
router.include_router(upload_router)
router.include_router(field_router)
router.include_router(asset_router)
