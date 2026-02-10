# api_main.py (updated)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.db.session import init_db, close_db
from backend.api.routes_auth import router as auth_router
from backend.api.routes_missions import router as missions_router
from backend.api.routes_websocket import router as websockets_router
from backend.api.routes_telemetry_control import router as telemetry_control_router

from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    # Startup
    logger.info("Starting application...")
    await init_db()

    # DON'T start WebSocket telemetry manager here anymore
    # It will be started when a mission begins
    logger.info("Application started - Telemetry WebSocket will start on mission launch")

    yield

    # Shutdown
    logger.info("Shutting down application...")

    # Check if telemetry is running and stop it
    from backend.messaging.websocket import telemetry_manager
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


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    from backend.messaging.websocket import telemetry_manager
    return {
        "status": "healthy",
        "websocket_active": telemetry_manager._running,
        "active_connections": len(telemetry_manager.active_connections)
    }