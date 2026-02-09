import json, ssl, time, socket
import paho.mqtt.client as mqtt
from backend.config import settings
from backend.db.repository import TelemetryRepository
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
    def __init__(self, host: str, port: int = 1883, username: str = "", password: str = "",
                 use_tls: bool = False, ca_certs: Optional[str] = None, client_id: Optional[str] = None,
                 connect_timeout: int = 10, max_retries: int = 20, retry_backoff_s: float = 0.5):

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
        self._emitted_frame_ids = deque(maxlen=200)        # de-dupe recent frames
        self._last_telemetry: Dict[str, Any] = {}

        if username:
            self.client.username_pw_set(username, password)

        if use_tls:
            if ca_certs:
                self.client.tls_set(ca_certs=ca_certs, tls_version=ssl.PROTOCOL_TLS_CLIENT)
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
            raise RuntimeError(f"MQTT connect failed to {host}:{port} after {max_retries} attempts: {last_err}")

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
            logging.info("[MQTT] Connected.")
        else:
            logging.info(f"[MQTT] Connect failed rc={rc}")

    def _on_disconnect(self, client, userdata, rc, flags, properties=None):
        logging.info(f"[MQTT] Disconnected rc={rc}")

    def _on_log(self, client, userdata, level, buf):
        if level >= mqtt.MQTT_LOG_ERR:
            logging.info(f"[MQTT] {buf}")

    # subscribe to broker

    def subscribe_to_topics(self, flight_id: int):
        """Subscribe to the ardupilot telemetry topic"""

        self._current_flight_id = flight_id
        logging.info(f"MQTT client: Setting flight_id to {flight_id}")
        self.client.subscribe(self.topic, qos=1)
        self.client.on_message = self._on_message
        logging.info(f"MQTT client: Subscribed to topic {self.topic} with flight_id {flight_id}")


    def _on_subscribe(self, client, userdata, mid, granted_qos, properties=None):
        logging.info(f"[MQTT] Subscribed mid={mid} qos={granted_qos}")
        self.client.on_subscribe = self._on_subscribe


    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages from ardupilot"""
        try:
            if msg.topic == settings.telemetry_topic:
                logging.debug(f"Received MQTT message on topic {msg.topic}")
                payload = json.loads(msg.payload.decode())
                logging.debug(f"Message payload type: {payload.get('mavpackettype', 'UNKNOWN')}")
                # self._process_telemetry_messages(payload)
                self._process_raw_event(payload)
        except Exception as e:
            logging.error(f"Error processing MQTT message: {e}")


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
                time_unix_usec = datetime.fromtimestamp(time_unix_usec/1_000_000, tz=timezone.utc)

            timestamp = _parse_ts(payload.get("timestamp"))

            item = {
                "flight_id": self._current_flight_id,
                "msg_type": payload.get("mavpackettype"),
                "time_boot_ms": payload.get("time_boot_ms", None),
                "time_unix_usec": time_unix_usec,
                "timestamp": timestamp,
                "payload": payload,
            }
            
            logging.debug(f"Processing raw event: msg_type={item['msg_type']}, flight_id={self._current_flight_id}")
            
            self._raw_event_queue.put_nowait(item)
            logging.debug(f"Enqueued event to raw_event_queue, queue size: {self._raw_event_queue.qsize()}")
            
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
            logging.error(f"Error processing raw event: {e}")


    #
    # def _process_telemetry_messages(self, payload: Dict[str, Any]):
    #     mav_type  = payload.get("mavpackettype")
    #     if not mav_type:
    #         return
    #     try:
    #         if mav_type == "GLOBAL_POSITION_INT":
    #             self._last_telemetry.update({
    #                 'lat': payload.get('lat', 0) / 1e7,
    #                 'lon': payload.get('lon', 0) / 1e7,
    #                 'alt': payload.get('alt', 0) / 1e3,
    #                 'frame_id': payload.get('time_boot_ms')  # used for de-dupe
    #             })
    #         elif mav_type == "VFR_HUD":
    #             self._last_telemetry.update({
    #                 'groundspeed': payload.get('groundspeed', 0.0),
    #                 'heading': payload.get('heading', 0.0),
    #             })
    #         elif mav_type == "PLANE_MODE":
    #             self._last_telemetry.update({'mode': payload.get('name') or payload.get('mode', 'UNKNOWN')})
    #         elif mav_type == "BATTERY_STATUS":
    #             # Prefer % from BATTERY_STATUS if provided
    #             if 'battery_remaining' in payload:
    #                 self._last_telemetry.update({'battery_remaining': payload.get('battery_remaining')})
    #         elif mav_type == "SYS_STATUS":
    #             # SYS_STATUS also includes voltage_battery (mV), current_battery (cA), battery_remaining (%)
    #             v_mv = payload.get('voltage_battery')
    #             if v_mv is not None:
    #                 self._last_telemetry['battery_voltage'] = v_mv / 1000.0
    #             i_cA = payload.get('current_battery')
    #             if i_cA is not None and i_cA >= 0:
    #                 self._last_telemetry['battery_current'] = i_cA / 100.0
    #             if 'battery_remaining' in payload:
    #                 self._last_telemetry['battery_remaining'] = payload['battery_remaining']
    #         elif mav_type == "SYSTEM_TIME":
    #             ts = payload.get('time_unix_usec')
    #             if ts:
    #                 self._last_telemetry['system_time'] = datetime.fromtimestamp(ts/1_000_000, tz=timezone.utc)
    #
    #         # ----- When we have a complete "frame", enqueue it -----
    #         required = ('lat','lon','alt','heading','groundspeed','mode')
    #         if all(k in self._last_telemetry for k in required):
    #             fid = self._last_telemetry.get('frame_id')
    #             if fid is None or fid not in self._emitted_frame_ids:
    #                 row = dict(self._last_telemetry)
    #                 row['flight_id'] = self._current_flight_id
    #                 if self._ingest_queue is not None:
    #                     try:
    #                         # Non-blocking: if full, drop oldest to keep up
    #                         self._ingest_queue.put_nowait(row)
    #                     except asyncio.QueueFull:
    #                         try:
    #                             _ = self._ingest_queue.get_nowait()
    #                             self._ingest_queue.task_done()
    #                         except Exception:
    #                             pass
    #                         self._ingest_queue.put_nowait(row)
    #                 if fid is not None:
    #                     self._emitted_frame_ids.append(fid)
    #     except Exception as e:
    #         logging.error(f"Error processing {mav_type}: {e}")