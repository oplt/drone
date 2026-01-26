"""
MQTT Telemetry Bridge for Flask Dashboard
Subscribes to MQTT broker and forwards real-time telemetry to SocketIO clients
"""

import json
import threading
import time
import logging
import paho.mqtt.client as mqtt
from flask_socketio import SocketIO
from config import settings
from typing import Dict, Any, Optional, Deque, TypedDict
from collections import deque
from datetime import datetime, timezone


class TelemetryPayload(TypedDict, total=False):
    latitude: float
    longitude: float
    altitude: float
    heading: float
    groundspeed: float
    mode: str
    battery_percentage: Optional[float]
    battery_voltage: Optional[float]
    battery_current: Optional[float]
    timestamp: str


class MqttTelemetryBridge:
    """Bridge MQTT telemetry to SocketIO for real-time dashboard updates"""

    def __init__(self, socketio: SocketIO):
        self.socketio = socketio
        self.mqtt_client = None
        self.connected = False
        self._last_telemetry: Dict[str, Any] = {}
        self._emitted_frame_ids: Deque[int] = deque(maxlen=200)  # De-duplicate frames
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._last_emit_time: float = 0.0
        self._emit_interval = 0.5  # Emit at least every 500ms if we have position data
        self._periodic_thread = None

    def start(self):
        """Start MQTT connection and subscription"""
        if self._running:
            logging.warning("MQTT bridge already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._connect_and_subscribe, daemon=True)
        self._thread.start()

        # Start periodic emission thread to ensure regular updates
        self._periodic_thread = threading.Thread(
            target=self._periodic_emit_worker, daemon=True
        )
        self._periodic_thread.start()

    def stop(self):
        """Stop MQTT connection"""
        self._running = False
        if self.mqtt_client:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except Exception as e:
                logging.error(f"Error stopping MQTT client: {e}")
        self.connected = False

    def _connect_and_subscribe(self):
        """Connect to MQTT broker and subscribe to telemetry topic"""
        try:
            # Use unique client_id to avoid conflicts when Flask reloads in debug mode
            import os
            import time

            unique_id = f"flask_dashboard_telemetry_{os.getpid()}_{int(time.time())}"
            self.mqtt_client = mqtt.Client(
                client_id=unique_id,
                protocol=mqtt.MQTTv311,
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            )

            if settings.mqtt_user and settings.mqtt_pass:
                self.mqtt_client.username_pw_set(settings.mqtt_user, settings.mqtt_pass)

            self.mqtt_client.on_connect = self._on_connect
            self.mqtt_client.on_disconnect = self._on_disconnect
            self.mqtt_client.on_message = self._on_message
            self.mqtt_client.on_log = self._on_log

            # Connect with retries
            max_retries = 10
            for attempt in range(max_retries):
                if not self._running:
                    return

                try:
                    self.mqtt_client.connect(
                        settings.mqtt_broker, settings.mqtt_port, keepalive=60
                    )
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        logging.warning(
                            f"MQTT connection attempt {attempt + 1} failed: {e}, retrying..."
                        )
                        time.sleep(2)
                    else:
                        logging.error(
                            f"Failed to connect to MQTT broker after {max_retries} attempts: {e}"
                        )
                        return

            self.mqtt_client.loop_start()

            # Wait for connection
            for _ in range(50):  # Wait up to 5 seconds
                if self.connected:
                    break
                time.sleep(0.1)

            if self.connected:
                logging.info(
                    f"✅ MQTT telemetry bridge connected to {settings.mqtt_broker}:{settings.mqtt_port}"
                )
            else:
                logging.error("MQTT telemetry bridge failed to connect")

        except Exception as e:
            logging.error(f"Error in MQTT bridge connection: {e}", exc_info=True)

    def _periodic_emit_worker(self):
        """Periodic worker that emits latest telemetry at regular intervals"""
        while self._running:
            try:
                time.sleep(self._emit_interval)

                if not self.connected:
                    continue

                with self._lock:
                    # Emit if we have position data and enough time has passed
                    has_position = (
                        "lat" in self._last_telemetry and "lon" in self._last_telemetry
                    )
                    current_time = time.time()

                    if (
                        has_position
                        and (current_time - self._last_emit_time) >= self._emit_interval
                    ):
                        telemetry_data = {
                            "telemetry": {
                                "altitude": float(self._last_telemetry.get("alt", 0)),
                                "latitude": float(self._last_telemetry.get("lat", 0)),
                                "longitude": float(self._last_telemetry.get("lon", 0)),
                                "battery_percentage": self._last_telemetry.get(
                                    "battery_remaining"
                                ),
                                "heading": float(
                                    self._last_telemetry.get("heading", 0)
                                ),
                                "groundspeed": float(
                                    self._last_telemetry.get("groundspeed", 0)
                                ),
                                "mode": str(
                                    self._last_telemetry.get("mode", "UNKNOWN")
                                ),
                                "battery_voltage": self._last_telemetry.get(
                                    "battery_voltage"
                                ),
                                "battery_current": self._last_telemetry.get(
                                    "battery_current"
                                ),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            },
                            "flight_id": None,
                            "flight_status": "in_progress",
                        }

                        self.socketio.emit(
                            "telemetry_update", telemetry_data, namespace="/"
                        )
                        self._last_emit_time = current_time

            except Exception as e:
                logging.error(f"Error in periodic emit worker: {e}")
                time.sleep(1)

    def _on_connect(self, client, _userdata, _flags, rc, _properties=None):
        """MQTT connection callback"""
        if rc == 0:
            self.connected = True
            logging.info("MQTT telemetry bridge: Connected to broker")
            # Subscribe to telemetry topic
            topic = settings.telemetry_topic
            client.subscribe(topic, qos=1)
            logging.info(f"MQTT telemetry bridge: Subscribed to {topic}")
        else:
            self.connected = False
            logging.error(f"MQTT telemetry bridge: Connection failed with code {rc}")

    def _on_disconnect(self, client, _userdata, rc, _flags, _properties=None):
        """MQTT disconnection callback"""
        self.connected = False

        # Check if this is a normal disconnect (not an error)
        if hasattr(rc, "is_disconnect_packet_from_server"):
            # This is a DisconnectFlags object (MQTT v5 or paho-mqtt internal)
            if not rc.is_disconnect_packet_from_server:
                # Normal disconnect, don't log as warning
                logging.debug("MQTT telemetry bridge: Disconnected normally")
            else:
                logging.warning("MQTT telemetry bridge: Disconnected by server")
        else:
            # rc is an integer (MQTT v3.1.1)
            if rc == 0:
                logging.debug("MQTT telemetry bridge: Disconnected normally")
            else:
                logging.warning(f"MQTT telemetry bridge: Disconnected (rc={rc})")

        # Only attempt to reconnect if still running and it was an unexpected disconnect
        if self._running:
            # Wait a bit before reconnecting to avoid rapid reconnection loops
            time.sleep(5)
            if not self.connected:
                try:
                    logging.info("MQTT telemetry bridge: Attempting to reconnect...")
                    client.reconnect()
                except Exception as e:
                    logging.error(f"MQTT reconnect error: {e}")

    def _on_log(self, _client, _userdata, level, buf):
        """MQTT log callback - only log warnings and errors, not debug info"""
        # paho-mqtt logs CONNECT/SUBSCRIBE as ERROR level but they're actually normal operations
        # Only log actual errors and warnings
        if level >= mqtt.MQTT_LOG_WARNING:
            # Filter out normal connection messages that are logged as errors
            if (
                "CONNECT" in buf
                or "SUBSCRIBE" in buf
                or "SUBACK" in buf
                or "CONNACK" in buf
            ):
                # These are normal operations, log at debug level if needed
                logging.debug(f"MQTT: {buf}")
            else:
                logging.warning(f"MQTT: {buf}")

    def _on_message(self, _client, _userdata, msg):
        """Handle incoming MQTT telemetry messages"""
        if not self._running:
            return

        try:
            if msg.topic == settings.telemetry_topic:
                payload = json.loads(msg.payload.decode())
                self._process_telemetry_message(payload)
        except Exception as e:
            logging.error(f"Error processing MQTT message: {e}")

    def _process_telemetry_message(self, payload: Dict[str, Any]):
        """Process telemetry message and update _last_telemetry"""
        mav_type = payload.get("mavpackettype")
        if not mav_type:
            return

        with self._lock:
            try:
                if mav_type == "GLOBAL_POSITION_INT":
                    self._last_telemetry.update(
                        {
                            "lat": payload.get("lat", 0) / 1e7,
                            "lon": payload.get("lon", 0) / 1e7,
                            "alt": payload.get("alt", 0) / 1e3,
                            "frame_id": payload.get("time_boot_ms"),
                        }
                    )
                elif mav_type == "VFR_HUD":
                    self._last_telemetry.update(
                        {
                            "groundspeed": payload.get("groundspeed", 0.0),
                            "heading": payload.get("heading", 0.0),
                        }
                    )
                elif mav_type == "HEARTBEAT":
                    mode = payload.get("mode") or payload.get("name")
                    if mode is None:
                        mode = str(payload.get("custom_mode", "UNKNOWN"))
                    self._last_telemetry["mode"] = mode
                elif mav_type == "BATTERY_STATUS":
                    voltages = payload.get("voltages") or []
                    v0 = voltages[0] if voltages else None
                    if v0 is not None:
                        self._last_telemetry["battery_voltage"] = float(v0) / 1000.0
                    cur_cA = payload.get("current_battery")
                    if cur_cA is not None:
                        self._last_telemetry["battery_current"] = float(cur_cA) / 100.0
                    if "battery_remaining" in payload:
                        self._last_telemetry["battery_remaining"] = payload.get(
                            "battery_remaining"
                        )
                elif mav_type == "SYS_STATUS":
                    v_mv = payload.get("voltage_battery")
                    if v_mv is not None:
                        self._last_telemetry["battery_voltage"] = float(v_mv) / 1000.0
                    i_cA = payload.get("current_battery")
                    if i_cA is not None and i_cA >= 0:
                        self._last_telemetry["battery_current"] = float(i_cA) / 100.0
                    if "battery_remaining" in payload:
                        self._last_telemetry["battery_remaining"] = payload.get(
                            "battery_remaining"
                        )

                # Emit telemetry if we have any meaningful data (don't wait for complete frame)
                # This ensures more frequent updates even if some fields are missing
                has_position = (
                    "lat" in self._last_telemetry and "lon" in self._last_telemetry
                )
                has_other_data = any(
                    k in self._last_telemetry
                    for k in ("mode", "battery_remaining", "groundspeed", "heading")
                )

                # Emit if we have position data OR other meaningful telemetry
                if has_position or has_other_data:
                    fid = self._last_telemetry.get("frame_id")
                    current_time = time.time()

                    # Emit if:
                    # 1. We have a new frame_id (not seen before), OR
                    # 2. Enough time has passed since last emission (for position updates)
                    should_emit = False
                    if fid is not None:
                        if fid not in self._emitted_frame_ids:
                            should_emit = True
                            self._emitted_frame_ids.append(fid)
                        elif current_time - self._last_emit_time > self._emit_interval:
                            # Emit periodically even with same frame_id if position might have changed
                            should_emit = True
                    elif current_time - self._last_emit_time > self._emit_interval:
                        # No frame_id but we have data - emit periodically
                        should_emit = True

                    if should_emit:
                        # Emit to all SocketIO clients
                        # Format matches what dashboard.js expects
                        # Use defaults for missing fields
                        telemetry_data = {
                            "telemetry": {
                                "altitude": float(self._last_telemetry.get("alt", 0)),
                                "latitude": float(self._last_telemetry.get("lat", 0)),
                                "longitude": float(self._last_telemetry.get("lon", 0)),
                                "battery_percentage": self._last_telemetry.get(
                                    "battery_remaining"
                                ),
                                "heading": float(
                                    self._last_telemetry.get("heading", 0)
                                ),
                                "groundspeed": float(
                                    self._last_telemetry.get("groundspeed", 0)
                                ),
                                "mode": str(
                                    self._last_telemetry.get("mode", "UNKNOWN")
                                ),
                                "battery_voltage": self._last_telemetry.get(
                                    "battery_voltage"
                                ),
                                "battery_current": self._last_telemetry.get(
                                    "battery_current"
                                ),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            },
                            "flight_id": None,  # Not available from MQTT directly
                            "flight_status": "in_progress",  # Assume in progress if receiving telemetry
                        }

                        # Emit to all connected clients
                        try:
                            self.socketio.emit(
                                "telemetry_update", telemetry_data, namespace="/"
                            )
                            self._last_emit_time = current_time
                        except Exception as e:
                            logging.error(f"Error emitting telemetry update: {e}")

            except Exception as e:
                logging.error(f"Error processing telemetry message: {e}")

    def get_latest_telemetry(self) -> Optional[Dict[str, Any]]:
        """Get latest telemetry data (thread-safe) - returns data even if some fields are missing"""
        with self._lock:
            # Return data if we have at least position data (lat/lon) or any telemetry
            # Don't require all fields to be present
            if not self._last_telemetry:
                return None

            # At minimum, we should have some telemetry data
            if len(self._last_telemetry) == 0:
                return None

            # Build telemetry dict with available data, using defaults for missing fields
            telemetry: TelemetryPayload = {}

            # Position data (most important)
            if "lat" in self._last_telemetry and "lon" in self._last_telemetry:
                telemetry["latitude"] = float(self._last_telemetry["lat"])
                telemetry["longitude"] = float(self._last_telemetry["lon"])
            else:
                # If no position, still return other telemetry if available
                if len(self._last_telemetry) <= 2:  # Only has mode or similar
                    return None

            # Optional fields with defaults
            telemetry["altitude"] = float(self._last_telemetry.get("alt", 0))
            telemetry["heading"] = float(self._last_telemetry.get("heading", 0))
            telemetry["groundspeed"] = float(self._last_telemetry.get("groundspeed", 0))
            telemetry["mode"] = str(self._last_telemetry.get("mode", "UNKNOWN"))
            batt_remaining = self._last_telemetry.get("battery_remaining")
            telemetry["battery_percentage"] = (
                float(batt_remaining) if batt_remaining is not None else None
            )
            batt_v = self._last_telemetry.get("battery_voltage")
            telemetry["battery_voltage"] = float(batt_v) if batt_v is not None else None
            batt_c = self._last_telemetry.get("battery_current")
            telemetry["battery_current"] = float(batt_c) if batt_c is not None else None
            telemetry["timestamp"] = datetime.now(timezone.utc).isoformat()

            return {
                "telemetry": telemetry,
                "flight_id": None,
                "flight_status": "in_progress",
            }


# Global bridge instance with lock to prevent multiple instances
_telemetry_bridge: Optional[MqttTelemetryBridge] = None
_bridge_lock = threading.Lock()


def get_telemetry_bridge(socketio: SocketIO) -> MqttTelemetryBridge:
    """Get or create telemetry bridge instance (thread-safe singleton)"""
    global _telemetry_bridge

    with _bridge_lock:
        if _telemetry_bridge is None:
            _telemetry_bridge = MqttTelemetryBridge(socketio)
            _telemetry_bridge.start()
            logging.info("MQTT telemetry bridge instance created and started")
        elif not _telemetry_bridge._running:
            # Bridge exists but stopped, restart it
            logging.info("MQTT telemetry bridge was stopped, restarting...")
            _telemetry_bridge.start()
        else:
            # Bridge is already running, just return it
            logging.debug("MQTT telemetry bridge already running, reusing instance")

    return _telemetry_bridge
