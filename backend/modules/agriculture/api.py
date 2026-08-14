"""Agriculture HTTP API — aggregates concern-specific routers under /agriculture."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from backend.core.config.runtime import settings
from backend.core.rate_limit import enforce_rate_limit
from backend.modules.agriculture.analysis_orchestration import agriculture_analysis_orchestration
from backend.modules.agriculture.live import LiveAgricultureProcessor, decode_rgb_frame
from backend.modules.agriculture.p5_service import agriculture_safety_service
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.routers import analysis, fields, flights, live, media, ops, planning
from backend.modules.agriculture.routers.common import (
    AGRICULTURE_SCHEMA_VERSION,
    _live_processors,
    _media_inventory,
    _owned_flight,
    _parse_spatial_bbox,
    get_live_processor,
)
from backend.modules.agriculture.service import agriculture_service
from backend.modules.agriculture.storage import agriculture_storage
from backend.observability.audit import emit_audit_event

# Re-export route handlers and helpers that tests import from this module.
from backend.modules.agriculture.routers.analysis import (  # noqa: F401
    create_agriculture_export,
    create_analysis_run,
    register_frame_manifest,
)
from backend.modules.agriculture.routers.flights import get_media_inventory  # noqa: F401
from backend.modules.agriculture.routers.live import ingest_telemetry, live_advisory  # noqa: F401
from backend.modules.agriculture.routers.media import initiate_upload  # noqa: F401


def agriculture_contract_headers(response: Response) -> None:
    response.headers["X-Agriculture-Schema-Version"] = AGRICULTURE_SCHEMA_VERSION


router = APIRouter(
    prefix="/agriculture",
    tags=["agriculture"],
    dependencies=[Depends(agriculture_contract_headers)],
)

router.include_router(ops.router)
router.include_router(fields.router)
router.include_router(planning.router)
router.include_router(flights.router)
router.include_router(live.router)
router.include_router(media.router)
router.include_router(analysis.router)

__all__ = [
    "AGRICULTURE_SCHEMA_VERSION",
    "LiveAgricultureProcessor",
    "_live_processors",
    "_media_inventory",
    "_owned_flight",
    "_parse_spatial_bbox",
    "agriculture_analysis_orchestration",
    "agriculture_contract_headers",
    "agriculture_repository",
    "agriculture_safety_service",
    "agriculture_service",
    "agriculture_storage",
    "create_agriculture_export",
    "create_analysis_run",
    "decode_rgb_frame",
    "emit_audit_event",
    "enforce_rate_limit",
    "get_live_processor",
    "get_media_inventory",
    "ingest_telemetry",
    "initiate_upload",
    "live_advisory",
    "register_frame_manifest",
    "router",
    "settings",
]
