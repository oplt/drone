from __future__ import annotations

from fastapi import APIRouter

from backend.modules.analytics.api.overview_routes import router as overview_router
from backend.modules.analytics.api.telemetry_summary_routes import (
    router as telemetry_summary_router,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])
router.include_router(overview_router)
router.include_router(telemetry_summary_router)
