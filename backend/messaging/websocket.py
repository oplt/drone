import asyncio
import logging
import threading
import time
from typing import Dict, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect
from pymavlink import mavutil
from backend.config import settings
import orjson
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Client:
    ws: WebSocket
    q: asyncio.Queue
    task: asyncio.Task


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


        # Last telemetry data for new connections
        self.last_telemetry: Dict = {
            "position": {"lat": 0, "lon": 0, "alt": 0, "relative_alt": 0},
            "attitude": {"roll": 0, "pitch": 0, "yaw": 0},
            "battery": {"voltage": 0, "current": 0, "remaining": 0, "temperature": 0},
            "status": {"groundspeed": 0, "airspeed": 0, "heading": 0, "throttle": 0, "climb": 0},
            "mode": "DISCONNECTED",
            "armed": False,
            "timestamp": 0
        }


    async def connect(self, websocket: WebSocket):
        await websocket.accept()

        q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=2)

        async def writer():
            try:
                while True:
                    payload = await q.get()
                    await websocket.send_text(payload.decode("utf-8"))
            except WebSocketDisconnect:
                pass
            except asyncio.CancelledError:
                raise
            except Exception:
                # keep this low-noise unless you're debugging
                pass

        task = asyncio.create_task(writer())

        with self._lock:
            self._clients[websocket] = Client(ws=websocket, q=q, task=task)

        # initial snapshot
        if self.last_telemetry["timestamp"] > 0:
            payload = orjson.dumps({"type": "telemetry", "data": self.last_telemetry})
            self._enqueue_latest(q, payload)


    def disconnect(self, websocket: WebSocket):
        with self._lock:
            client = self._clients.pop(websocket, None)
        if client:
            client.task.cancel()


    def _enqueue_latest(self, q: asyncio.Queue[bytes], payload: bytes):
        if q.full():
            try:
                q.get_nowait()  # drop oldest
            except asyncio.QueueEmpty:
                pass
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            # if still full, drop newest too (rare)
            pass


    async def broadcast_bytes(self, payload: bytes):
        # Broadcast to _clients queues (NOT active_connections)
        with self._lock:
            clients = list(self._clients.values())

        for c in clients:
            self._enqueue_latest(c.q, payload)


    async def broadcast(self, message: dict):
        """Broadcast message to all connected WebSocket clients"""
        dead_connections = []

        with self._lock:
            connections_to_notify = list(self.active_connections)

        for connection in connections_to_notify:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to WebSocket: {e}")
                dead_connections.append(connection)

        # Clean up dead connections
        if dead_connections:
            with self._lock:
                for conn in dead_connections:
                    if conn in self.active_connections:
                        self.active_connections.remove(conn)

    def start_telemetry_stream(self, mavlink_connection_str: str = None):
        """Start the MAVLink telemetry streaming thread"""
        if self._running:
            logger.warning("Telemetry stream already running")
            return

        # Store the main event loop
        try:
            self._event_loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.error("No running event loop found. WebSocket broadcasting may not work.")
            self._event_loop = None

        conn_str = mavlink_connection_str or settings.drone_conn_mavproxy
        self._running = True

        def telemetry_worker():
            """Worker thread that reads MAVLink messages and broadcasts via WebSocket"""
            try:
                # Connect to MAVLink
                self.mav_conn = mavutil.mavlink_connection(conn_str, autoreconnect=True)
                logger.info(f"Connected to MAVLink for telemetry: {conn_str}")

                # Wait for heartbeat to ensure connection
                self.mav_conn.wait_heartbeat()
                logger.info("MAVLink heartbeat received")

                # Request data streams
                try:
                    self.mav_conn.mav.request_data_stream_send(
                        self.mav_conn.target_system,
                        self.mav_conn.target_component,
                        mavutil.mavlink.MAV_DATA_STREAM_ALL,
                        10,  # 10 Hz
                        1
                    )
                except Exception as e:
                    logger.warning(f"Could not request data streams: {e}")

                # Message buffer to reduce broadcast frequency
                message_buffer = []
                last_broadcast_time = time.time()
                broadcast_interval = 0.1  # Broadcast every 100ms (10 Hz)

                while self._running:
                    try:
                        # Read MAVLink message
                        msg = self.mav_conn.recv_match(
                            blocking=False,
                            timeout=0.1,  # Short timeout for responsive shutdown
                            type=[
                                'GLOBAL_POSITION_INT',
                                'VFR_HUD',
                                'BATTERY_STATUS',
                                'ATTITUDE',
                                'HEARTBEAT',
                                'GPS_RAW_INT',
                                'SYS_STATUS'
                            ]
                        )

                        if msg:
                            msg_dict = msg.to_dict()
                            telemetry_data = self._process_mavlink_message(msg_dict)

                            # Update last telemetry
                            if telemetry_data:
                                self.last_telemetry.update(telemetry_data)
                                self.last_telemetry["timestamp"] = time.time()

                                # Add to buffer for batched broadcasting
                                message_buffer.append(telemetry_data)

                        # Broadcast at fixed intervals (not on every message)
                        current_time = time.time()
                        if (current_time - last_broadcast_time >= broadcast_interval and
                                message_buffer and self._event_loop is not None):

                            # Create consolidated telemetry update
                            consolidated_update = {}
                            for update in message_buffer:
                                consolidated_update.update(update)

                            # Create broadcast message
                            broadcast_msg = {
                                "type": "telemetry",
                                "data": {**self.last_telemetry, **consolidated_update}
                            }

                            payload = orjson.dumps(broadcast_msg)

                            # Schedule broadcast in the main event loop
                            try:
                                asyncio.run_coroutine_threadsafe(
                                    self.broadcast_bytes(payload),
                                    self._event_loop
                                )
                            except Exception as e:
                                logger.error(f"Failed to schedule broadcast: {e}")

                            # Reset buffer and timer
                            message_buffer.clear()
                            last_broadcast_time = current_time

                    except Exception as e:
                        if self._running:  # Only log if we're still running
                            logger.error(f"Error processing MAVLink message: {e}")
                        time.sleep(0.01)

            except Exception as e:
                logger.error(f"Telemetry worker error: {e}")
            finally:
                if self.mav_conn:
                    self.mav_conn.close()
                self._running = False
                logger.info("Telemetry stream stopped")

        # Start telemetry worker thread
        self._telemetry_thread = threading.Thread(
            target=telemetry_worker,
            daemon=True,
            name="TelemetryWebSocketWorker"
        )
        self._telemetry_thread.start()
        logger.info("Telemetry WebSocket stream started")

    def _process_mavlink_message(self, msg_dict: dict) -> dict:
        """Process MAVLink message and extract relevant telemetry"""
        msg_type = msg_dict.get('mavpackettype', '')
        processed = {}

        try:
            if msg_type == 'GLOBAL_POSITION_INT':
                lat = msg_dict.get('lat', 0)
                lon = msg_dict.get('lon', 0)

                # Only process if coordinates are valid (not 0,0)
                if lat != 0 or lon != 0:
                    processed["position"] = {
                        "lat": float(lat) / 1e7,
                        "lon": float(lon) / 1e7,
                        "alt": float(msg_dict.get('alt', 0)) / 1e3,
                        "relative_alt": float(msg_dict.get('relative_alt', 0)) / 1e3
                    }

            elif msg_type == 'VFR_HUD':
                processed["status"] = {
                    "groundspeed": float(msg_dict.get('groundspeed', 0)),
                    "airspeed": float(msg_dict.get('airspeed', 0)),
                    "heading": float(msg_dict.get('heading', 0)),
                    "throttle": float(msg_dict.get('throttle', 0)),
                    "alt": float(msg_dict.get('alt', 0)),
                    "climb": float(msg_dict.get('climb', 0))
                }

            elif msg_type == 'BATTERY_STATUS':
                voltages = msg_dict.get('voltages', [0])
                voltage = float(voltages[0]) / 1000 if voltages and voltages[0] > 0 else 0.0

                processed["battery"] = {
                    "voltage": voltage,
                    "current": float(msg_dict.get('current_battery', 0)) / 100,
                    "remaining": int(msg_dict.get('battery_remaining', -1)),
                    "temperature": float(msg_dict.get('temperature', 0))
                }

            elif msg_type == 'ATTITUDE':
                processed["attitude"] = {
                    "roll": float(msg_dict.get('roll', 0)),
                    "pitch": float(msg_dict.get('pitch', 0)),
                    "yaw": float(msg_dict.get('yaw', 0)),
                    "rollspeed": float(msg_dict.get('rollspeed', 0)),
                    "pitchspeed": float(msg_dict.get('pitchspeed', 0)),
                    "yawspeed": float(msg_dict.get('yawspeed', 0))
                }

            elif msg_type == 'HEARTBEAT':
                mode_mapping = {
                    0: 'STABILIZE', 1: 'ACRO', 2: 'ALT_HOLD', 3: 'AUTO',
                    4: 'GUIDED', 5: 'LOITER', 6: 'RTL', 7: 'CIRCLE',
                    8: 'POSITION', 9: 'LAND', 10: 'OF_LOITER', 11: 'DRIFT',
                    13: 'SPORT', 14: 'FLIP', 15: 'AUTOTUNE', 16: 'POSHOLD',
                    17: 'BRAKE', 18: 'THROW', 19: 'AVOID_ADSB', 20: 'GUIDED_NOGPS',
                    21: 'SMART_RTL'
                }
                custom_mode = msg_dict.get('custom_mode', 0)
                processed["mode"] = mode_mapping.get(custom_mode, 'UNKNOWN')
                processed["armed"] = bool(msg_dict.get('base_mode', 0) & 0x80)

        except Exception as e:
            logger.error(f"Error processing {msg_type} message: {e}")

        return processed

    def stop_telemetry_stream(self):
        """Stop the telemetry streaming thread"""
        self._running = False
        if self._telemetry_thread and self._telemetry_thread.is_alive():
            self._telemetry_thread.join(timeout=2.0)
        logger.info("Telemetry WebSocket stream stopped")


# Global WebSocket manager instance
telemetry_manager = TelemetryWebSocketManager()