import json
import ssl
import time
import socket
import paho.mqtt.client as mqtt
from config import settings
from db.repository import TelemetryRepository
from typing import Dict, Any, Optional
import asyncio
from datetime import datetime, timezone
from collections import deque
import logging


def _parse_ts(ts_raw):
    if ts_raw is None:
        return None
    if isinstance(ts_raw, (int, float)):
        return datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
    if isinstance(ts_raw, str):
        try:
            # handle ISO8601-ish strings
            return datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


class MqttClient:
    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: str = "",
        password: str = "",
        use_tls: bool = False,
        ca_certs: Optional[str] = None,
        client_id: Optional[str] = None,
        connect_timeout: int = 10,
        max_retries: int = 20,
        retry_backoff_s: float = 0.5,
    ):
        self.client = mqtt.Client(
            client_id=client_id or "",
            protocol=mqtt.MQTTv311,
            transport="tcp",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )

        self.repo = TelemetryRepository()
        self._current_flight_id: Optional[int] = None
        self._ingest_queue: Optional["asyncio.Queue[dict]"] = None
        self._raw_event_queue: Optional["asyncio.Queue[dict]"] = None
        self._emitted_frame_ids: deque[int] = deque(maxlen=200)  # de-dupe recent frames
        self._last_telemetry: Dict[str, Any] = {}
        self._event_loop: Optional[asyncio.AbstractEventLoop] = (
            None  # For thread-safe async operations
        )
        self._early_message_buffer: list = (
            []
        )  # Buffer messages received before flight_id is set
        self._max_buffer_size = 1000  # Max messages to buffer

        if username:
            self.client.username_pw_set(username, password)

        if use_tls:
            if ca_certs:
                self.client.tls_set(
                    ca_certs=ca_certs, tls_version=ssl.PROTOCOL_TLS_CLIENT
                )
            else:
                self.client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
            self.client.tls_insecure_set(False)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_log = self._on_log
        self.client.on_subscribe = self._on_subscribe
        self.topic = settings.telemetry_topic

        # Robust connect with retries
        attempt, delay = 0, retry_backoff_s
        last_err = None
        while attempt < max_retries:
            try:
                self.client.connect(host, port, keepalive=60)
                break
            except (ConnectionRefusedError, TimeoutError, socket.error) as e:
                last_err = e
                time.sleep(delay)
                delay = min(delay * 2, 8.0)  # exponential backoff capped
                attempt += 1
        else:
            raise RuntimeError(
                f"MQTT connect failed to {host}:{port} after {max_retries} attempts: {last_err}"
            )

        self.client.loop_start()

    def is_connected(self) -> bool:
        try:
            return bool(self.client.is_connected())
        except Exception:
            return False

    def reconnect(self) -> bool:
        try:
            self.client.reconnect()
            return True
        except Exception as e:
            logging.error(f"[MQTT] Reconnect failed: {e}")
            return False

    def publish(self, topic: str, payload, qos: int = 0, retain: bool = False):
        if not isinstance(payload, (str, bytes)):
            payload = json.dumps(payload)
        self.client.publish(topic, payload, qos=qos, retain=retain)

    def close(self):
        try:
            self.client.loop_stop()
        finally:
            try:
                self.client.disconnect()
            except Exception:
                pass

    # ---- callbacks ----
    def _on_connect(self, client, _userdata, _flags, rc, _properties=None):
        # In MQTT v3.1.1 rc is an int; 0 = success
        if rc == 0:
            logging.info("[MQTT] Connected.")
        else:
            logging.info(f"[MQTT] Connect failed rc={rc}")

    def _on_disconnect(self, client, _userdata, rc, _flags, _properties=None):
        logging.info(f"[MQTT] Disconnected rc={rc}")

    def _on_log(self, _client, _userdata, level, buf):
        if level >= mqtt.MQTT_LOG_ERR:
            logging.info(f"[MQTT] {buf}")

    # subscribe to broker

    def subscribe_to_topics(self, flight_id: int):
        """Subscribe to the ardupilot telemetry topic"""

        try:
            self._current_flight_id = flight_id
            logging.info(f"MQTT client: Setting flight_id to {flight_id}")
            self.client.subscribe(self.topic, qos=1)
            self.client.on_message = self._on_message
            logging.info(
                f"MQTT client: Subscribed to topic {self.topic} with flight_id {flight_id}"
            )
        except Exception as e:
            logging.error(f"MQTT client: Subscribe failed: {e}")
            return False

        # Process buffered early messages if any
        if self._early_message_buffer and self._event_loop:
            logging.info(
                f"Processing {len(self._early_message_buffer)} buffered early messages"
            )
            for payload in self._early_message_buffer:
                try:
                    asyncio.run_coroutine_threadsafe(
                        self._async_enqueue_event(self._create_event_item(payload)),
                        self._event_loop,
                    )
                except Exception as e:
                    logging.error(f"Error processing buffered message: {e}")
            self._early_message_buffer.clear()
        return True

    def _on_subscribe(self, _client, _userdata, mid, granted_qos, _properties=None):
        logging.info(f"[MQTT] Subscribed mid={mid} qos={granted_qos}")

    def _on_message(self, _client, _userdata, msg):
        """Handle incoming MQTT messages from ardupilot (runs in paho-mqtt thread)"""
        try:
            if msg.topic == settings.telemetry_topic:
                logging.debug(f"Received MQTT message on topic {msg.topic}")
                payload = json.loads(msg.payload.decode())
                logging.debug(
                    f"Message payload type: {payload.get('mavpackettype', 'UNKNOWN')}"
                )
                # Bridge from sync callback to async queue safely
                self._process_raw_event_threadsafe(payload)
                self._process_telemetry_threadsafe(payload)
            elif msg.topic.startswith("drone/commands/"):
                # Handle command messages
                logging.info(f"Received command on topic {msg.topic}")
                payload = json.loads(msg.payload.decode())
                # Store command for processing by orchestrator
                if hasattr(self, "_command_callback") and self._command_callback:
                    self._command_callback(payload)
        except Exception as e:
            logging.error(f"Error processing MQTT message: {e}")

    def set_command_callback(self, callback):
        """Set callback for command messages"""
        self._command_callback = callback

    def attach_ingest_queue(self, q: "asyncio.Queue[dict]"):
        self._ingest_queue = q

    def attach_raw_event_queue(self, q: "asyncio.Queue[dict]"):
        self._raw_event_queue = q

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the event loop for thread-safe async operations from MQTT callbacks"""
        self._event_loop = loop

    def _process_raw_event_threadsafe(self, payload: Dict[str, Any]):
        """
        Thread-safe bridge from MQTT callback (sync) to async queue.
        This method runs in paho-mqtt's thread and schedules async work.
        """
        # If flight_id is not set yet, buffer the message
        if self._current_flight_id is None:
            if len(self._early_message_buffer) < self._max_buffer_size:
                self._early_message_buffer.append(payload)
                logging.debug(
                    f"Buffered early message (buffer size: {len(self._early_message_buffer)})"
                )
            else:
                logging.warning("Early message buffer full, dropping message")
            return

        if not self._raw_event_queue:
            logging.warning("Raw event queue not attached, cannot process events")
            return

        if not self._event_loop:
            logging.warning(
                "Event loop not set, cannot safely enqueue events. Using fallback."
            )
            # Fallback: try direct put_nowait (not ideal but better than nothing)
            try:
                item = self._create_event_item(payload)
                self._raw_event_queue.put_nowait(item)
            except Exception as e:
                logging.error(f"Fallback event processing failed: {e}")
            return

        # Schedule async processing in the event loop
        try:
            # Create the item in the sync context
            item = self._create_event_item(payload)

            # Schedule async enqueue operation
            asyncio.run_coroutine_threadsafe(
                self._async_enqueue_event(item), self._event_loop
            )
            # Don't wait for result to avoid blocking MQTT callback thread
            # Errors will be logged in the async coroutine
        except Exception as e:
            logging.error(f"Error scheduling async event processing: {e}")

    def _process_telemetry_threadsafe(self, payload: Dict[str, Any]):
        """
        Best-effort derivation of a compact telemetry row for the `telemetry` table.
        Runs in paho-mqtt thread; enqueues into `_ingest_queue` on the asyncio loop.
        """
        if self._current_flight_id is None or not self._ingest_queue:
            return

        mav_type = payload.get("mavpackettype")
        if not mav_type:
            return

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
                # Use any explicit mode name if provided; otherwise store custom_mode as string
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
            elif mav_type == "SYSTEM_TIME":
                ts = payload.get("time_unix_usec")
                if ts:
                    try:
                        self._last_telemetry["system_time"] = datetime.fromtimestamp(
                            float(ts) / 1_000_000, tz=timezone.utc
                        )
                    except Exception:
                        pass

            required = ("lat", "lon", "alt", "heading", "groundspeed", "mode")
            if not all(k in self._last_telemetry for k in required):
                return

            fid = self._last_telemetry.get("frame_id")
            if fid is not None and fid in self._emitted_frame_ids:
                return

            row = {
                "lat": float(self._last_telemetry["lat"]),
                "lon": float(self._last_telemetry["lon"]),
                "alt": float(self._last_telemetry["alt"]),
                "heading": float(self._last_telemetry["heading"]),
                "groundspeed": float(self._last_telemetry["groundspeed"]),
                "mode": str(self._last_telemetry["mode"]),
                "battery_voltage": self._last_telemetry.get("battery_voltage"),
                "battery_current": self._last_telemetry.get("battery_current"),
                "battery_remaining": self._last_telemetry.get("battery_remaining"),
                "system_time": self._last_telemetry.get("system_time"),
                "frame_id": fid,
            }

            if self._event_loop:
                asyncio.run_coroutine_threadsafe(
                    self._async_enqueue_ingest(row), self._event_loop
                )
            else:
                # Fallback (may be unsafe if called from non-loop thread, but keeps data flowing)
                self._ingest_queue.put_nowait(row)

            if fid is not None:
                self._emitted_frame_ids.append(fid)

        except Exception as e:
            logging.error(f"Error deriving telemetry row: {e}")

    async def _async_enqueue_ingest(self, row: Dict[str, Any]):
        if not self._ingest_queue:
            return
        try:
            self._ingest_queue.put_nowait(row)
        except asyncio.QueueFull:
            try:
                _ = self._ingest_queue.get_nowait()
                self._ingest_queue.task_done()
            except Exception:
                pass
            try:
                self._ingest_queue.put_nowait(row)
            except asyncio.QueueFull:
                # give up
                pass

    def _create_event_item(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create event item from payload (thread-safe, no async operations)"""
        time_unix_usec = payload.get("time_unix_usec")
        if time_unix_usec:
            time_unix_usec = datetime.fromtimestamp(
                time_unix_usec / 1_000_000, tz=timezone.utc
            )

        timestamp = _parse_ts(payload.get("timestamp"))

        return {
            "flight_id": self._current_flight_id,
            "msg_type": payload.get("mavpackettype"),
            "time_boot_ms": payload.get("time_boot_ms", None),
            "time_unix_usec": time_unix_usec,
            "timestamp": timestamp,
            "payload": payload,
        }

    async def _async_enqueue_event(self, item: Dict[str, Any]):
        """
        Async coroutine to safely enqueue events with proper error handling.
        This runs in the async event loop.
        """
        if not self._raw_event_queue:
            logging.warning("Raw event queue not attached")
            return

        try:
            logging.debug(
                f"Processing raw event: msg_type={item['msg_type']}, flight_id={item['flight_id']}"
            )

            # Try to put item in queue
            try:
                self._raw_event_queue.put_nowait(item)
                logging.debug(
                    f"Enqueued event to raw_event_queue, queue size: {self._raw_event_queue.qsize()}"
                )
            except asyncio.QueueFull:
                logging.warning("Raw event queue is full, dropping oldest event")
                # Drop oldest to maintain recency
                try:
                    dropped_item = self._raw_event_queue.get_nowait()
                    self._raw_event_queue.task_done()
                    logging.debug(
                        f"Dropped message type: {dropped_item.get('msg_type', 'UNKNOWN')}"
                    )
                except asyncio.QueueEmpty:
                    pass
                except Exception as e:
                    logging.error(f"Error dropping oldest event: {e}")

                # Try again to add new event
                try:
                    self._raw_event_queue.put_nowait(item)
                    logging.debug("Enqueued event after dropping oldest")
                except asyncio.QueueFull:
                    logging.error(
                        "Queue still full after dropping oldest event - message lost"
                    )

        except Exception as e:
            logging.error(f"Error in async event enqueue: {e}", exc_info=True)
