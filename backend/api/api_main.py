from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.db.session import init_db, close_db
from backend.api.routes_auth import router as auth_router
from backend.api.routes_flights import router as missions_router
from backend.api.routes_websocket import router as websockets_router
from backend.api.routes_telemetry_control import router as telemetry_control_router
from backend.api.routes_video import router as video_router
from backend.api.routes_settings import router as settings_router
from backend.api.routes_analytics import router as analytics_router
from backend.utils.config_runtime import get_runtime_settings
from backend.db.repository import SettingsRepository
from contextlib import asynccontextmanager
import logging
from backend.config import setup_logging
import asyncio

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
    telemetry_manager._event_loop = asyncio.get_running_loop()
    logger.info("WebSocket manager initialized")

    yield

    # Shutdown
    logger.info("Shutting down application...")

    # Check if telemetry is running and stop it
    if telemetry_manager._running:
        telemetry_manager.stop_telemetry_stream()
        logger.info("Telemetry WebSocket server stopped")

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
        routes.append({
            "path": route.path,
            "name": route.name,
            "methods": list(route.methods) if hasattr(route, "methods") else None
        })
    return {"routes": routes}
