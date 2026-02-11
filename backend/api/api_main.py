# api_main.py (updated)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.db.session import init_db, close_db
from backend.api.routes_auth import router as auth_router
from backend.api.routes_flights import router as missions_router
from backend.api.routes_websocket import router as websockets_router
from backend.api.routes_telemetry_control import router as telemetry_control_router
from backend.api.routes_video import router as video_router

from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    # Startup
    logger.info("Starting application...")
    await init_db()

    # Initialize WebSocket manager
    from backend.messaging.websocket import telemetry_manager

    await telemetry_manager.initialize()
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


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    from backend.messaging.websocket import telemetry_manager

    return {
        "status": "healthy",
        "websocket_active": telemetry_manager._running,
        "active_connections": len(telemetry_manager.active_connections),
    }
