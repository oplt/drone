import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routes.routes_alerts import router as alerts_router
from backend.api.routes.routes_analytics import router as analytics_router
from backend.api.routes.routes_animal_farm import router as animal_farm_router
from backend.api.routes.routes_auth import router as auth_router
from backend.api.routes.routes_field import router as fields_router
from backend.api.routes.routes_flights import router as missions_router
from backend.api.routes.routes_geofence import router as geofence_router
from backend.api.routes.routes_mapping import router as mapping_router
from backend.api.routes.routes_ml import router as ml_router
from backend.api.routes.routes_patrol_debug import router as patrol_debug_router
from backend.api.routes.routes_settings import router as settings_router
from backend.api.routes.routes_telemetry_control import (
    router as telemetry_control_router,
)
from backend.api.routes.routes_video import router as video_router
from backend.api.routes.routes_warehouse import router as warehouse_router
from backend.api.routes.routes_websocket import router as websockets_router
from backend.config import setup_logging
from backend.db.repository.settings_repo import SettingsRepository
from backend.db.session import close_db, init_db
from backend.flight.cleanup_jobs import start_cleanup_jobs, stop_cleanup_jobs
from backend.flight.restart_recovery import recover_interrupted_missions
from backend.main import _build_orchestrator
from backend.services.alerts.engine import alert_engine
from backend.utils.config_runtime import get_runtime_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    setup_logging()
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

    await close_db()


# Create FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)

# React dev servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(missions_router)
app.include_router(websockets_router)
app.include_router(telemetry_control_router)
app.include_router(video_router)
app.include_router(settings_router)
app.include_router(analytics_router)
app.include_router(geofence_router)
app.include_router(animal_farm_router)
app.include_router(fields_router)
app.include_router(mapping_router)
app.include_router(warehouse_router)
app.include_router(alerts_router)
app.include_router(ml_router)
app.include_router(patrol_debug_router)

mapping_assets_dir = Path(
    os.getenv("PHOTOGRAMMETRY_STORAGE_DIR", "backend/storage/mapping")
).resolve()
mapping_assets_dir.mkdir(parents=True, exist_ok=True)
serve_public_mapping_assets = os.getenv("PHOTOGRAMMETRY_PUBLIC_STATIC_ASSETS", "1").lower() in {
    "1",
    "true",
    "yes",
}
if serve_public_mapping_assets:
    app.mount(
        "/mapping-assets",
        StaticFiles(directory=str(mapping_assets_dir)),
        name="mapping-assets",
    )
else:
    logger.info("Public mapping asset mount disabled; use signed mapping asset gateway routes")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    from backend.messaging.websocket import telemetry_manager

    return {
        "status": "healthy",
        "websocket_active": telemetry_manager._running,
        "active_connections": len(telemetry_manager.active_connections),
    }


@app.get("/debug/routes")
async def debug_routes():
    """List all registered routes (debug only)"""
    routes = []
    for route in app.routes:
        routes.append(
            {
                "path": route.path,
                "name": route.name,
                "methods": list(route.methods) if hasattr(route, "methods") else None,
            }
        )
    return {"routes": routes}
