"""
SocketIO event handlers for real-time telemetry updates
Now uses MQTT subscription instead of database polling
"""

from flask_login import current_user
from flask_socketio import emit, disconnect
import logging

# Store active connections
active_connections = set()


def register_events(socketio):
    """Register SocketIO event handlers"""
    # Initialize MQTT telemetry bridge (singleton, will reuse if already exists)
    from flask_app.app.dashboard.mqtt_telemetry_bridge import get_telemetry_bridge

    # Get or create bridge instance (thread-safe)
    bridge = get_telemetry_bridge(socketio)

    # Only log if this is a new initialization
    if bridge.connected:
        logging.debug("MQTT telemetry bridge already initialized and connected")
    else:
        logging.info(
            "✅ MQTT telemetry bridge initialized for SocketIO (connecting...)"
        )

    @socketio.on("connect")
    def handle_connect():
        """Handle client connection"""
        if not current_user.is_authenticated:
            disconnect()
            return False

        active_connections.add(current_user.id)
        logging.info(f"Client connected: User {current_user.id}")
        emit("connected", {"message": "Connected to real-time telemetry stream"})

        # Send latest telemetry immediately if available
        latest = bridge.get_latest_telemetry()
        if latest:
            emit("telemetry_update", latest)

    @socketio.on("disconnect")
    def handle_disconnect():
        """Handle client disconnection"""
        if current_user.is_authenticated:
            active_connections.discard(current_user.id)
            logging.info(f"Client disconnected: User {current_user.id}")

    @socketio.on("request_telemetry")
    def handle_telemetry_request():
        """Handle explicit telemetry request - get from MQTT bridge"""
        if not current_user.is_authenticated:
            return

        # Get latest telemetry from MQTT bridge (real-time, not database)
        latest = bridge.get_latest_telemetry()
        if latest:
            emit("telemetry_update", latest)
        else:
            # No telemetry available yet
            emit(
                "telemetry_update",
                {
                    "telemetry": None,
                    "message": "Waiting for telemetry data from MQTT...",
                },
            )
