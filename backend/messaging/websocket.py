import asyncio
import logging
import threading
import time
from typing import Dict, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from pymavlink import mavutil
from backend.config import settings
import orjson
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class Client:
    ws: WebSocket
    q: asyncio.Queue
    task: asyncio.Task
    connected_time: float
    client_host: str | None = None
    client_port: int | None = None
    user_agent: str | None = None


class TelemetryWebSocketManager:
    """Manages WebSocket connections for real-time telemetry broadcasting"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.mav_conn: Optional[mavutil.mavlink_connection] = None
        self._running = False
        self._telemetry_thread: Optional[threading.Thread] = None
        self._clients: dict[WebSocket, Client] = {}
        self._lock = threading.Lock()
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._broadcast_queue: asyncio.Queue = None

        # Last telemetry data for new connections
        self.last_telemetry: Dict = {
            "position": {"lat": 0, "lon": 0, "alt": 0, "relative_alt": 0},
            "attitude": {"roll": 0, "pitch": 0, "yaw": 0},
            "battery": {"voltage": 0, "current": 0, "remaining": 0, "temperature": 0},
            "status": {
                "groundspeed": 0,
                "airspeed": 0,
                "heading": 0,
                "throttle": 0,
                "climb": 0,
            },
            "mode": "DISCONNECTED",
            "armed": False,
            "timestamp": 0,
        }

    async def initialize(self):
        """Initialize the broadcast queue"""
        self._broadcast_queue = asyncio.Queue()

    # websocket.py (update the connect method)
    async def connect(self, websocket: WebSocket):
        """Accept and manage a new WebSocket connection"""
        try:
            # IMPORTANT: Don't call websocket.accept() here!
            # It's already called in the route handler

            # Create queue for this client
            q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=10)

            async def writer():
                """Task that writes messages to this specific client"""
                try:
                    while True:
                        payload = await q.get()
                        try:
                            # Decode bytes to string for JSON validation
                            message_str = payload.decode("utf-8")

                            # Send as text message
                            await websocket.send_text(message_str)

                        except (UnicodeDecodeError, json.JSONDecodeError) as e:
                            logger.warning(f"Invalid message format: {e}")
                            continue
                        except (WebSocketDisconnect, RuntimeError):
                            break  # Connection is dead
                        except Exception as e:
                            logger.error(f"Error sending to client: {e}")
                            break

                except asyncio.CancelledError:
                    logger.debug("Writer task cancelled")
                except Exception as e:
                    logger.error(f"Writer task error: {e}")
                finally:
                    # Clean up
                    with self._lock:
                        if websocket in self._clients:
                            del self._clients[websocket]
                        self.active_connections.discard(websocket)

            # Create writer task
            task = asyncio.create_task(writer())

            client_host = getattr(getattr(websocket, "client", None), "host", None)
            client_port = getattr(getattr(websocket, "client", None), "port", None)
            try:
                user_agent = websocket.headers.get("user-agent")
            except Exception:
                user_agent = None

            with self._lock:
                self.active_connections.add(websocket)
                self._clients[websocket] = Client(
                    ws=websocket,
                    q=q,
                    task=task,
                    connected_time=time.time(),
                    client_host=client_host,
                    client_port=client_port,
                    user_agent=user_agent,
                )

            logger.info(
                "✅ WebSocket connected. Active connections: %s (client=%s:%s ua=%s)",
                len(self.active_connections),
                client_host,
                client_port,
                user_agent,
            )

            # Send initial telemetry data if available
            if self.last_telemetry["timestamp"] > 0:
                payload = orjson.dumps(
                    {"type": "telemetry", "data": self.last_telemetry}
                )
                await q.put(payload)

            # Return the writer task so the route can monitor it
            return task

        except Exception as e:
            logger.error(f"❌ Failed to setup WebSocket connection: {e}")
            raise

    async def _keep_alive(self, websocket: WebSocket, writer_task: asyncio.Task):
        """Keep the connection alive and handle disconnection"""
        try:
            # Keep connection alive by listening for messages
            while True:
                try:
                    # Wait for client message (with timeout)
                    data = await asyncio.wait_for(
                        websocket.receive_text(), timeout=30.0
                    )

                    # Handle ping messages
                    if data == "ping":
                        try:
                            await websocket.send_text("pong")
                        except Exception:
                            break  # Connection is dead

                except asyncio.TimeoutError:
                    # Send keep-alive ping
                    try:
                        await websocket.send_json(
                            {"type": "keepalive", "timestamp": time.time()}
                        )
                    except Exception:
                        break  # Connection is dead

                except WebSocketDisconnect:
                    break
                except RuntimeError as e:
                    if "after sending 'websocket.close'" in str(e):
                        break  # Connection already closed
                    raise

        except WebSocketDisconnect:
            logger.debug("WebSocket disconnected normally")
        except RuntimeError as e:
            if "after sending 'websocket.close'" in str(e):
                logger.debug("WebSocket already closed")
            else:
                logger.error(f"WebSocket runtime error: {e}")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
        finally:
            # Cancel writer task
            if not writer_task.done():
                writer_task.cancel()
                try:
                    await writer_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

            # Clean up
            with self._lock:
                if websocket in self._clients:
                    del self._clients[websocket]
                self.active_connections.discard(websocket)

            logger.info(
                f"🔌 WebSocket disconnected. Active connections: {len(self.active_connections)}"
            )

    def disconnect(self, websocket: WebSocket):
        """Disconnect a specific WebSocket client"""
        with self._lock:
            client = self._clients.pop(websocket, None)
            self.active_connections.discard(websocket)

        if client:
            client.task.cancel()
            logger.info("Manually disconnected WebSocket")

    def _enqueue_latest(self, q: asyncio.Queue[bytes], payload: bytes):
        """Add payload to client queue, dropping old messages if queue is full"""
        try:
            if q.full():
                try:
                    q.get_nowait()  # Drop oldest message
                except asyncio.QueueEmpty:
                    pass

            q.put_nowait(payload)
        except asyncio.QueueFull:
            # Queue still full, skip this message
            pass

    async def broadcast_bytes(self, payload: bytes):
        """Broadcast message to all connected clients"""
        if not self._clients:
            return

        with self._lock:
            clients = list(self._clients.values())

        disconnected_clients = []

        for client in clients:
            try:
                # Check if WebSocket is still connected
                if client.ws.client_state == WebSocketState.CONNECTED:
                    self._enqueue_latest(client.q, payload)
                else:
                    disconnected_clients.append(client.ws)
            except Exception as e:
                logger.error(f"Failed to broadcast to client: {e}")
                disconnected_clients.append(client.ws)

        # Clean up disconnected clients
        if disconnected_clients:
            for ws in disconnected_clients:
                self.disconnect(ws)

    async def broadcast(self, message: dict):
        """Broadcast JSON message to all connected clients"""
        try:
            payload = orjson.dumps(message)
            await self.broadcast_bytes(payload)
        except Exception as e:
            logger.error(f"Broadcast error: {e}")

    def start_telemetry_stream(self, mavlink_connection_str: str = None):
        """Start the MAVLink telemetry streaming thread"""
        if self._running:
            logger.warning("Telemetry stream already running")
            return True

        try:
            self._event_loop = asyncio.get_event_loop()
        except RuntimeError:
            # Create new event loop if needed
            self._event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._event_loop)

        conn_str = mavlink_connection_str or settings.drone_conn_mavproxy

        # Validate MAVLink connection string
        if not conn_str:
            logger.error("❌ No MAVLink connection string provided")
            return False

        self._running = True

        def telemetry_worker():
            """Worker thread that reads MAVLink messages and broadcasts via WebSocket"""
            mav_conn = None
            telemetry_initialized = False

            try:
                logger.info(f"📡 Connecting to MAVLink: {conn_str}")

                # Connect to MAVLink with timeout
                mav_conn = mavutil.mavlink_connection(
                    conn_str, autoreconnect=True, retries=3, source_system=255
                )
                # Expose for debug/introspection
                self.mav_conn = mav_conn

                # Wait for heartbeat with timeout
                heartbeat = mav_conn.wait_heartbeat(timeout=10)
                if not heartbeat:
                    logger.error("❌ MAVLink heartbeat timeout")
                    self._running = False
                    return

                logger.info("✅ MAVLink heartbeat received")

                # Request data streams
                try:
                    mav_conn.mav.request_data_stream_send(
                        mav_conn.target_system,
                        mav_conn.target_component,
                        mavutil.mavlink.MAV_DATA_STREAM_ALL,
                        10,  # 10 Hz
                        1,
                    )
                    logger.info("📊 Requested MAVLink data streams")
                except Exception as e:
                    logger.warning(f"⚠️ Could not request data streams: {e}")

                telemetry_initialized = True

                # Message buffer for batching
                message_buffer = []
                last_broadcast_time = time.time()
                broadcast_interval = 0.1  # 10 Hz
                last_heartbeat_time = time.time()

                while self._running:
                    try:
                        # Check for heartbeat every 5 seconds
                        current_time = time.time()
                        if current_time - last_heartbeat_time > 5:
                            if not mav_conn or not self._check_mavlink_connection(
                                mav_conn
                            ):
                                logger.warning(
                                    "MAVLink connection lost, attempting to reconnect..."
                                )
                                mav_conn.close()
                                mav_conn = mavutil.mavlink_connection(
                                    conn_str, autoreconnect=True
                                )
                                last_heartbeat_time = current_time

                            last_heartbeat_time = current_time

                        # Read MAVLink message
                        msg = mav_conn.recv_match(
                            blocking=False,
                            timeout=0.05,  # Short timeout for responsive shutdown
                            type=[
                                "GLOBAL_POSITION_INT",
                                "VFR_HUD",
                                "BATTERY_STATUS",
                                "ATTITUDE",
                                "HEARTBEAT",
                                "GPS_RAW_INT",
                                "SYS_STATUS",
                            ],
                        )

                        if msg:
                            msg_dict = msg.to_dict()
                            telemetry_data = self._process_mavlink_message(msg_dict)

                            # Update last telemetry
                            if telemetry_data:
                                self.last_telemetry.update(telemetry_data)
                                self.last_telemetry["timestamp"] = time.time()
                                message_buffer.append(telemetry_data)

                        # Broadcast at fixed intervals
                        current_time = time.time()
                        if (
                            current_time - last_broadcast_time >= broadcast_interval
                            and message_buffer
                            and self._event_loop is not None
                        ):
                            # Create consolidated update
                            consolidated_update = {}
                            for update in message_buffer:
                                consolidated_update.update(update)

                            # Create broadcast message
                            broadcast_msg = {
                                "type": "telemetry",
                                "data": {**self.last_telemetry, **consolidated_update},
                            }

                            try:
                                payload = orjson.dumps(broadcast_msg)
                                with self._lock:
                                    has_active_connections = len(self._clients) > 0

                                if has_active_connections:
                                    # Schedule broadcast
                                    try:
                                        future = asyncio.run_coroutine_threadsafe(
                                            self.broadcast_bytes(payload),
                                            self._event_loop,
                                        )
                                        future.add_done_callback(
                                            lambda f: (
                                                f.exception() if f.exception() else None
                                            )
                                        )
                                    except Exception as e:
                                        logger.error(
                                            f"Failed to schedule broadcast: {e}"
                                        )

                                else:
                                    # No active connections, just update last_telemetry
                                    pass

                            except Exception as e:
                                logger.error(f"Failed to create broadcast payload: {e}")

                            # Reset buffer and timer
                            message_buffer.clear()
                            last_broadcast_time = current_time

                        # Small sleep to prevent CPU spinning
                        time.sleep(0.001)

                    except Exception as e:
                        if self._running:
                            logger.error(f"Error in telemetry worker: {e}")
                        time.sleep(0.1)

            except Exception as e:
                logger.error(f"❌ Telemetry worker failed: {e}")
                self._running = False
            finally:
                if mav_conn:
                    try:
                        mav_conn.close()
                    except:
                        pass
                self.mav_conn = None
                self._running = False
                logger.info("Telemetry worker stopped")

        # Start telemetry worker thread
        self._telemetry_thread = threading.Thread(
            target=telemetry_worker, daemon=True, name="TelemetryWebSocketWorker"
        )
        self._telemetry_thread.start()
        logger.info("🚀 Telemetry WebSocket stream started")
        return True

    def _check_mavlink_connection(self, mav_conn):
        """Check if MAVLink connection is still alive"""
        try:
            # Try to read a message with short timeout
            msg = mav_conn.recv_match(blocking=False, timeout=0.1)
            return True
        except:
            return False

    def _process_mavlink_message(self, msg_dict: dict) -> dict:
        """Process MAVLink message and extract relevant telemetry"""
        # ... (keep your existing _process_mavlink_message method unchanged) ...
        msg_type = msg_dict.get("mavpackettype", "")
        processed = {}

        try:
            if msg_type == "GLOBAL_POSITION_INT":
                lat = msg_dict.get("lat", 0)
                lon = msg_dict.get("lon", 0)

                # Only process if coordinates are valid (not 0,0)
                if lat != 0 or lon != 0:
                    processed["position"] = {
                        "lat": float(lat) / 1e7,
                        "lon": float(lon) / 1e7,
                        "alt": float(msg_dict.get("alt", 0)) / 1e3,
                        "relative_alt": float(msg_dict.get("relative_alt", 0)) / 1e3,
                    }

            elif msg_type == "GPS_RAW_INT":
                # Many stacks emit GPS_RAW_INT reliably even when GLOBAL_POSITION_INT is missing.
                # Units: lat/lon in 1e7 degrees, alt in mm.
                lat = msg_dict.get("lat", 0)
                lon = msg_dict.get("lon", 0)
                if lat != 0 or lon != 0:
                    processed["position"] = {
                        "lat": float(lat) / 1e7,
                        "lon": float(lon) / 1e7,
                        "alt": float(msg_dict.get("alt", 0)) / 1e3,
                        # relative_alt not available here; keep previous if any
                    }

            elif msg_type == "VFR_HUD":
                processed["status"] = {
                    "groundspeed": float(msg_dict.get("groundspeed", 0)),
                    "airspeed": float(msg_dict.get("airspeed", 0)),
                    "heading": float(msg_dict.get("heading", 0)),
                    "throttle": float(msg_dict.get("throttle", 0)),
                    "alt": float(msg_dict.get("alt", 0)),
                    "climb": float(msg_dict.get("climb", 0)),
                }

            elif msg_type == "BATTERY_STATUS":
                voltages = msg_dict.get("voltages", [0])
                voltage = (
                    float(voltages[0]) / 1000 if voltages and voltages[0] > 0 else 0.0
                )

                processed["battery"] = {
                    "voltage": voltage,
                    "current": float(msg_dict.get("current_battery", 0)) / 100,
                    "remaining": int(msg_dict.get("battery_remaining", -1)),
                    "temperature": float(msg_dict.get("temperature", 0)),
                }

            elif msg_type == "ATTITUDE":
                processed["attitude"] = {
                    "roll": float(msg_dict.get("roll", 0)),
                    "pitch": float(msg_dict.get("pitch", 0)),
                    "yaw": float(msg_dict.get("yaw", 0)),
                    "rollspeed": float(msg_dict.get("rollspeed", 0)),
                    "pitchspeed": float(msg_dict.get("pitchspeed", 0)),
                    "yawspeed": float(msg_dict.get("yawspeed", 0)),
                }

            elif msg_type == "HEARTBEAT":
                mode_mapping = {
                    0: "STABILIZE",
                    1: "ACRO",
                    2: "ALT_HOLD",
                    3: "AUTO",
                    4: "GUIDED",
                    5: "LOITER",
                    6: "RTL",
                    7: "CIRCLE",
                    8: "POSITION",
                    9: "LAND",
                    10: "OF_LOITER",
                    11: "DRIFT",
                    13: "SPORT",
                    14: "FLIP",
                    15: "AUTOTUNE",
                    16: "POSHOLD",
                    17: "BRAKE",
                    18: "THROW",
                    19: "AVOID_ADSB",
                    20: "GUIDED_NOGPS",
                    21: "SMART_RTL",
                }
                custom_mode = msg_dict.get("custom_mode", 0)
                processed["mode"] = mode_mapping.get(custom_mode, "UNKNOWN")
                processed["armed"] = bool(msg_dict.get("base_mode", 0) & 0x80)

        except Exception as e:
            logger.error(f"Error processing {msg_type} message: {e}")

        return processed

    def stop_telemetry_stream(self):
        """Stop the telemetry streaming thread"""
        if not self._running:
            return

        self._running = False

        # Also disconnect all WebSocket clients
        with self._lock:
            clients = list(self._clients.keys())

        for websocket in clients:
            self.disconnect(websocket)

        if self._telemetry_thread and self._telemetry_thread.is_alive():
            self._telemetry_thread.join(timeout=3.0)

        logger.info("🛑 Telemetry WebSocket stream stopped")


# Global WebSocket manager instance
telemetry_manager = TelemetryWebSocketManager()
