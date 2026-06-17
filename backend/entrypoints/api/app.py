import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.core.config.runtime import settings, setup_logging
from backend.core.database.session import close_db, engine, init_db
from backend.core.errors.handlers import register_error_handlers
from backend.observability.correlation import CorrelationMiddleware
from backend.infrastructure.camera.runtime import shared_video_runtime
from backend.modules.admin.api import router as admin_router
from backend.modules.ai.api import router as ai_router
from backend.modules.alerts.api import router as alerts_router
from backend.modules.alerts.evaluation_service import alert_engine
from backend.modules.analytics.api import router as analytics_router
from backend.modules.automation.api import router as templates_router
from backend.modules.compliance.api import router as compliance_router
from backend.modules.deliverables.share_api import (
    router as deliverables_share_router,
)
from backend.modules.fields.api import router as fields_router
from backend.modules.fleet.api import router as fleet_router
from backend.modules.geofences.api import router as geofence_router
from backend.modules.identity.api import router as auth_router
from backend.modules.identity.api_keys import router as apikeys_router
from backend.modules.integrations.api import router as integrations_router
from backend.modules.integrations.webhooks.api import router as webhooks_router
from backend.modules.irrigation.api import router as irrigation_router
from backend.modules.irrigation.monitor import irrigation_monitor
from backend.modules.livestock.api import router as animal_farm_router
from backend.modules.mapping.api import router as mapping_router
from backend.modules.media.api import router as video_router
from backend.modules.missions.api.routes import router as missions_router
from backend.modules.observability.api import router as observability_router
from backend.modules.patrol.api import router as patrol_debug_router
from backend.modules.patrol.live_detection_api import router as live_detection_router
from backend.modules.patrol.vision_api import router as ml_router
from backend.modules.property_patrol.api import router as property_patrol_router
from backend.modules.settings.api import router as settings_router
from backend.modules.settings.repository import SettingsRepository
from backend.modules.settings.service import get_runtime_settings
from backend.modules.telemetry.api import (
    router as telemetry_control_router,
)
from backend.modules.telemetry.api import (
    runtime_router,
)
from backend.modules.telemetry.websocket_api import router as websockets_router
from backend.modules.vehicle_runtime.cleanup import start_cleanup_jobs, stop_cleanup_jobs
from backend.modules.video_analysis.api import router as video_analysis_router
from backend.modules.warehouse.api import router as warehouse_router
from backend.observability.metrics import setup_metrics
from backend.observability.tracing import setup_tracing

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    setup_logging(log_format=settings.log_format)
    # Startup
    logger.info("Starting application...")
    await init_db()

    # Load settings from DB once
    app.state.settings = await get_runtime_settings(SettingsRepository())

    start_cleanup_jobs()
    logger.info("Cleanup jobs started")

    await alert_engine.start()
    logger.info("Operational alert engine started")

    await irrigation_monitor.start()
    logger.info("Irrigation monitor started")

    yield

    # Shutdown
    logger.info("Shutting down application...")

    await shared_video_runtime.stop()

    await stop_cleanup_jobs()
    logger.info("Cleanup jobs stopped")

    await alert_engine.stop()
    logger.info("Operational alert engine stopped")

    await irrigation_monitor.stop()
    logger.info("Irrigation monitor stopped")

    await close_db()


# Create FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)
register_error_handlers(app)

@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"status": "ok"}

# Observability
setup_metrics(app)
setup_tracing(app, engine=engine)

# Request / correlation ID middleware
app.add_middleware(CorrelationMiddleware)

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
app.include_router(runtime_router)
app.include_router(video_router)
app.include_router(settings_router)
app.include_router(ai_router)
app.include_router(analytics_router)
app.include_router(geofence_router)
app.include_router(animal_farm_router)
app.include_router(fields_router)
app.include_router(irrigation_router)
app.include_router(mapping_router)
app.include_router(alerts_router)
app.include_router(ml_router)
app.include_router(patrol_debug_router)
app.include_router(live_detection_router)
app.include_router(property_patrol_router)
app.include_router(templates_router, prefix="/tasks")
app.include_router(apikeys_router, prefix="/tasks")
app.include_router(webhooks_router, prefix="/tasks")
app.include_router(compliance_router, prefix="/tasks")
app.include_router(fleet_router, prefix="/tasks")
app.include_router(integrations_router)
app.include_router(deliverables_share_router)
app.include_router(video_analysis_router)
app.include_router(warehouse_router)
app.include_router(observability_router)

mapping_assets_dir = Path(settings.PHOTOGRAMMETRY_STORAGE_DIR).resolve()
mapping_assets_dir.mkdir(parents=True, exist_ok=True)
serve_public_mapping_assets = (
    settings.photogrammetry_public_static_assets and settings.storage_backend != "s3"
)
if serve_public_mapping_assets:
    app.mount(
        "/mapping-assets",
        StaticFiles(directory=str(mapping_assets_dir)),
        name="mapping-assets",
    )
else:
    logger.info("Public mapping asset mount disabled; use signed mapping asset gateway routes")

irrigation_assets_dir = Path(settings.irrigation_storage_dir).resolve()
irrigation_assets_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/irrigation-assets",
    StaticFiles(directory=str(irrigation_assets_dir)),
    name="irrigation-assets",
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    from backend.infrastructure.messaging.websocket_publisher import telemetry_manager

    telemetry = telemetry_manager.runtime_snapshot()
    return {
        "status": "healthy",
        "websocket_active": telemetry["running"],
        "active_connections": telemetry["active_connections"],
        "telemetry_source_connected": telemetry["source_connected"],
        "last_telemetry_update": telemetry["last_update"],
    }
