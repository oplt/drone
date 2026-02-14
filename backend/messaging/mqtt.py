import json
import ssl
import time
import socket
import paho.mqtt.client as mqtt
from backend.config import settings
from backend.db.repository import TelemetryRepository
from typing import Dict, Any, Optional
import asyncio
from datetime import datetime, timezone
from collections import deque
import logging
from pymavlink import mavutil
import threading

logger = logging.getLogger(__name__)


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
            max_retries: int = 10,
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
        self._ingest_queue: "asyncio.Queue[dict]" = None
        self._raw_event_queue: "asyncio.Queue[dict]" = None
        self._emitted_frame_ids = deque(maxlen=200)  # de-dupe recent frames
        self._last_telemetry: Dict[str, Any] = {}
        self.client.on_subscribe = self._on_subscribe

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
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        # In MQTT v3.1.1 rc is an int; 0 = success
        if rc == 0:
            logger.info("[MQTT] Connected.")
        else:
            logger.info(f"[MQTT] Connect failed rc={rc}")

    def _on_disconnect(self, client, userdata, rc, flags, properties=None):
        logger.info(f"[MQTT] Disconnected rc={rc}")

    def _on_log(self, client, userdata, level, buf):
        if level >= mqtt.MQTT_LOG_ERR:
            logger.info(f"[MQTT] {buf}")

    def subscribe_to_topics(self, flight_id: int) -> bool:
        self._current_flight_id = flight_id
        logger.info("MQTT client: Setting flight_id to %s", flight_id)

        result, mid = self.client.subscribe(self.topic, qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            logger.error("MQTT subscribe failed: result=%s mid=%s", result, mid)
            return False

        self.client.on_message = self._on_message
        logger.info(
            "MQTT client: Subscribed to topic %s with flight_id %s",
            self.topic,
            flight_id,
        )
        return True

    def _on_subscribe(self, client, userdata, mid, granted_qos, properties=None):
        logger.info(f"[MQTT] Subscribed mid={mid} qos={granted_qos}")

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages from ardupilot"""
        try:
            if msg.topic == settings.telemetry_topic:
                logging.debug(f"Received MQTT message on topic {msg.topic}")
                payload = json.loads(msg.payload.decode())
                logging.debug(
                    f"Message payload type: {payload.get('mavpackettype', 'UNKNOWN')}"
                )
                # self._process_telemetry_messages(payload)
                self._process_raw_event(payload)
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")

    def attach_ingest_queue(self, q: "asyncio.Queue[dict]"):
        self._ingest_queue = q

    def attach_raw_event_queue(self, q: "asyncio.Queue[dict]"):
        self._raw_event_queue = q

    def _process_raw_event(self, payload: Dict[str, Any]):
        if not self._raw_event_queue:
            logging.warning("Raw event queue not attached, cannot process events")
            return
        try:
            time_unix_usec = payload.get("time_unix_usec")
            if time_unix_usec:
                time_unix_usec = datetime.fromtimestamp(
                    time_unix_usec / 1_000_000, tz=timezone.utc
                )

            timestamp = _parse_ts(payload.get("timestamp"))

            item = {
                "flight_id": self._current_flight_id,
                "msg_type": payload.get("mavpackettype"),
                "time_boot_ms": payload.get("time_boot_ms", None),
                "time_unix_usec": time_unix_usec,
                "timestamp": timestamp,
                "payload": payload,
            }

            logging.debug(
                f"Processing raw event: msg_type={item['msg_type']}, flight_id={self._current_flight_id}"
            )

            self._raw_event_queue.put_nowait(item)
            logging.debug(
                f"Enqueued event to raw_event_queue, queue size: {self._raw_event_queue.qsize()}"
            )

        except asyncio.QueueFull:
            logging.warning("Raw event queue is full, dropping oldest event")
            # drop oldest to maintain recency
            try:
                _ = self._raw_event_queue.get_nowait()
                self._raw_event_queue.task_done()
            except Exception:
                pass
            self._raw_event_queue.put_nowait(item)
        except Exception as e:
            logger.error(f"Error processing raw event: {e}")


class MqttPublisher:
    """
    MQTT Publisher that reads from MAVLink and publishes to MQTT broker
    """
    def __init__(self, mqtt_client: MqttClient = None, mqtt_topic: str = None):
        self.mqtt_topic = mqtt_topic or settings.telemetry_topic
        self.mqtt_client = mqtt_client

        self.drone_conn_str = settings.drone_conn_mavproxy
        self.mav_conn = None

        # Control flags
        self.is_running = False
        self.publisher_thread = None

        # Message types to filter
        self.message_types = [
            "GLOBAL_POSITION_INT",
            "VFR_HUD",
            "BATTERY_STATUS",
            "SYSTEM_TIME",
            "GPS_RAW_INT",
            "HEARTBEAT",
        ]


    def connect_mavlink(self):
        """Establish MAVLink connection"""
        try:
            self.mav_conn = mavutil.mavlink_connection(self.drone_conn_str)
            logger.info(f"[MQTT Publisher] Connected to MAVLink: {self.drone_conn_str}")
            return True
        except Exception as e:
            logger.error(f"[MQTT Publisher] Failed to connect to MAVLink: {e}")
            return False

    def start(self):
        """Start the MQTT publisher"""
        if self.is_running:
            logger.info("[MQTT Publisher] Already running")
            return False

        # Connect to MAVLink
        if not self.connect_mavlink():
            return False

        # Start publishing in a separate thread
        self.is_running = True
        self.publisher_thread = threading.Thread(
            target=self._publish_loop,
            name="MQTTPublisher",
            daemon=True
        )
        self.publisher_thread.start()

        logger.info("[MQTT Publisher] Started")
        return True

    def stop(self):
        """Stop the MQTT publisher"""
        if not self.is_running:
            logger.info("[MQTT Publisher] Not running")
            return

        logger.info("[MQTT Publisher] Stopping...")
        self.is_running = False

        # Wait for thread to finish
        if self.publisher_thread and self.publisher_thread.is_alive():
            self.publisher_thread.join(timeout=5)

        # Close connections
        if self.mqtt_client:
            self.mqtt_client.close()

        if self.mav_conn:
            self.mav_conn.close()

        logger.info("[MQTT Publisher] Stopped")

    def _publish_loop(self):
        """Main publishing loop (runs in separate thread)"""
        logger.info("[MQTT Publisher] Starting MAVLink to MQTT forwarding...")

        while self.is_running:
            try:
                msg = self.mav_conn.recv_match(
                    blocking=False,
                    timeout=1.0,
                    type=self.message_types
                )

                if msg and self.is_running:
                    # Convert MAVLink message to JSON
                    msg_dict = msg.to_dict()
                    msg_dict["timestamp"] = time.time()

                    # Publish to MQTT
                    if self.mqtt_client:
                        self.mqtt_client.publish(
                            self.mqtt_topic,
                            json.dumps(msg_dict)
                        )
                        logger.debug(f"[MQTT Publisher] Published {msg_dict.get('mavpackettype')} to {self.mqtt_topic}")

            except Exception as e:
                if self.is_running:
                    logger.error(f"[MQTT Publisher] Error in publish loop: {e}")
                    time.sleep(1)

    def is_alive(self):
        """Check if the publisher is running"""
        return self.is_running and (
                self.publisher_thread and self.publisher_thread.is_alive()
        )

    def set_message_types(self, message_types):
        """Update the message types to filter"""
        self.message_types = message_types
        logger.info(f"[MQTT Publisher] Updated message types: {self.message_types}")