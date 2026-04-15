import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from backend.api.routes.routes_admin import router as admin_router
from backend.api.routes.routes_alerts import router as alerts_router
from backend.api.routes.routes_analytics import router as analytics_router
from backend.api.routes.routes_animal_farm import router as animal_farm_router
from backend.api.routes.routes_apikeys import router as apikeys_router
from backend.api.routes.routes_auth import router as auth_router
from backend.api.routes.routes_compliance import router as compliance_router
from backend.api.routes.routes_deliverables_share import (
    router as deliverables_share_router,
)
from backend.api.routes.routes_field import router as fields_router
from backend.api.routes.routes_fleet import router as fleet_router
from backend.api.routes.routes_flights import router as missions_router
from backend.api.routes.routes_geofence import router as geofence_router
from backend.api.routes.routes_integrations import router as integrations_router
from backend.api.routes.routes_irrigation import router as irrigation_router
from backend.api.routes.routes_mapping import router as mapping_router
from backend.api.routes.routes_ml import router as ml_router
from backend.api.routes.routes_patrol_debug import router as patrol_debug_router
from backend.api.routes.routes_settings import router as settings_router
from backend.api.routes.routes_telemetry_control import (
    router as telemetry_control_router,
)
from backend.api.routes.routes_templates import router as templates_router
from backend.api.routes.routes_video import router as video_router
from backend.api.routes.routes_warehouse import router as warehouse_router
from backend.api.routes.routes_webhooks import router as webhooks_router
from backend.api.routes.routes_websocket import router as websockets_router
from backend.config import settings, setup_logging
from backend.db.repository.settings_repo import SettingsRepository
from backend.db.session import close_db, init_db
from backend.flight.cleanup_jobs import start_cleanup_jobs, stop_cleanup_jobs
from backend.flight.restart_recovery import recover_interrupted_missions
from backend.main import _build_orchestrator
from backend.observability.tracing import setup_tracing
from backend.services.alerts.engine import alert_engine
from backend.services.irrigation.monitor import irrigation_monitor
from backend.utils.config_runtime import get_runtime_settings

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    setup_logging(log_format=settings.log_format)
    # Startup
    logger.info("Starting application...")
    await init_db()

    # Load settings from DB once
    app.state.settings = await get_runtime_settings(SettingsRepository())

    # Initialize WebSocket manager
    from backend.messaging.websocket import telemetry_manager

    await telemetry_manager.initialize()
    logger.info("WebSocket manager initialized")

    orchestrator = await _build_orchestrator()
    orchestrator.bind_event_loop(asyncio.get_running_loop())
    orchestrator.start_background_workers()
    logger.info("Orchestrator runtime loop and background workers initialized")

    await recover_interrupted_missions(orchestrator)
    logger.info("Restart recovery check complete")

    start_cleanup_jobs()
    logger.info("Cleanup jobs started")

    await alert_engine.start()
    logger.info("Operational alert engine started")

    await irrigation_monitor.start()
    logger.info("Irrigation monitor started")

    yield

    # Shutdown
    logger.info("Shutting down application...")

    orchestrator = await _build_orchestrator()

    # Mark any active mission as failed before the process exits so it isn't
    # left in a non-terminal state that restart recovery must handle later.
    await recover_interrupted_missions(orchestrator)

    if orchestrator.telemetry_running():
        await orchestrator.stop_live_telemetry()
        logger.info("Orchestrator telemetry ingest stopped")

    await orchestrator.stop_background_workers()
    logger.info("Orchestrator background workers stopped")

    await stop_cleanup_jobs()
    logger.info("Cleanup jobs stopped")

    await alert_engine.stop()
    logger.info("Operational alert engine stopped")

    await irrigation_monitor.stop()
    logger.info("Irrigation monitor stopped")

    await close_db()


# Create FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)

# Prometheus metrics instrumentation
try:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        excluded_handlers=["/health", "/metrics"],
    ).instrument(app).expose(app, include_in_schema=False)
except ImportError:
    logger.warning("prometheus-fastapi-instrumentator not installed; /metrics endpoint disabled")

# OpenTelemetry tracing
setup_tracing(app)

# Request ID middleware
app.add_middleware(RequestIDMiddleware)

# React dev servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
        "HEAD",
    ],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(missions_router)
app.include_router(websockets_router)
app.include_router(telemetry_control_router)
app.include_router(video_router)
app.include_router(settings_router)
app.include_router(analytics_router)
app.include_router(geofence_router)
app.include_router(animal_farm_router)
app.include_router(fields_router)
app.include_router(irrigation_router)
app.include_router(mapping_router)
app.include_router(warehouse_router)
app.include_router(alerts_router)
app.include_router(ml_router)
app.include_router(patrol_debug_router)
app.include_router(templates_router, prefix="/tasks")
app.include_router(apikeys_router, prefix="/tasks")
app.include_router(webhooks_router, prefix="/tasks")
app.include_router(compliance_router, prefix="/tasks")
app.include_router(fleet_router, prefix="/tasks")
app.include_router(integrations_router)
app.include_router(deliverables_share_router)

mapping_assets_dir = Path(
    os.getenv("PHOTOGRAMMETRY_STORAGE_DIR", "backend/storage/mapping")
).resolve()
mapping_assets_dir.mkdir(parents=True, exist_ok=True)
serve_public_mapping_assets = (
    os.getenv("PHOTOGRAMMETRY_PUBLIC_STATIC_ASSETS", "1").lower() in {"1", "true", "yes"}
    and settings.storage_backend != "s3"
)
if serve_public_mapping_assets:
    app.mount(
        "/mapping-assets",
        StaticFiles(directory=str(mapping_assets_dir)),
        name="mapping-assets",
    )
else:
    logger.info("Public mapping asset mount disabled; use signed mapping asset gateway routes")

irrigation_assets_dir = Path(
    os.getenv("IRRIGATION_STORAGE_DIR", "backend/storage/irrigation")
).resolve()
irrigation_assets_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/irrigation-assets",
    StaticFiles(directory=str(irrigation_assets_dir)),
    name="irrigation-assets",
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    from backend.messaging.websocket import telemetry_manager

    telemetry = telemetry_manager.runtime_snapshot()
    return {
        "status": "healthy",
        "websocket_active": telemetry["running"],
        "active_connections": telemetry["active_connections"],
        "telemetry_source_connected": telemetry["source_connected"],
        "last_telemetry_update": telemetry["last_update"],
    }

