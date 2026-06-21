from __future__ import annotations

import json
import logging
import ssl
import time
from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

MessageHandler = Callable[[str, bytes], None]


class MqttSubscriber:
    """MQTT client that subscribes to topics and forwards payloads to a callback."""

    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: str = "",
        password: str = "",
        use_tls: bool = False,
        ca_certs: str | None = None,
        client_id: str | None = None,
        topics: list[tuple[str, int]] | None = None,
        on_message: MessageHandler | None = None,
        max_retries: int = 10,
        retry_backoff_s: float = 0.5,
    ) -> None:
        self._topics = list(topics or [])
        self._on_message = on_message
        self.client = mqtt.Client(
            client_id=client_id or "",
            protocol=mqtt.MQTTv311,
            transport="tcp",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )

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
        self.client.on_message = self._on_message_cb
        self.client.on_log = self._on_log

        attempt, delay = 0, retry_backoff_s
        last_err: Exception | None = None
        while attempt < max_retries:
            try:
                self.client.connect(host, port, keepalive=60)
                break
            except (OSError, ConnectionRefusedError, TimeoutError) as exc:
                last_err = exc
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
                attempt += 1
        else:
            raise RuntimeError(
                f"MQTT subscribe connect failed to {host}:{port} after {max_retries} attempts: {last_err}"
            )

        self.client.loop_start()

    def set_message_handler(self, on_message: MessageHandler | None) -> None:
        self._on_message = on_message

    def subscribe(self, topic: str, qos: int = 1) -> None:
        self._topics.append((topic, qos))
        self.client.subscribe(topic, qos=qos)

    def close(self) -> None:
        try:
            self.client.loop_stop()
        finally:
            try:
                self.client.disconnect()
            except Exception:
                pass

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: int, properties: Any = None) -> None:
        if rc == 0:
            logger.info("[MQTT] Subscriber connected.")
            for topic, qos in self._topics:
                client.subscribe(topic, qos=qos)
                logger.info("[MQTT] Subscribed to %s (qos=%s)", topic, qos)
        else:
            logger.warning("[MQTT] Subscriber connect failed rc=%s", rc)

    def _on_disconnect(self, client: Any, userdata: Any, rc: int, flags: Any = None, properties: Any = None) -> None:
        logger.info("[MQTT] Subscriber disconnected rc=%s", rc)

    def _on_message_cb(self, client: Any, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        if self._on_message is None:
            return
        try:
            self._on_message(msg.topic, msg.payload)
        except Exception:
            logger.exception("[MQTT] Patrol trigger message handler failed for topic=%s", msg.topic)

    def _on_log(self, client: Any, userdata: Any, level: int, buf: str) -> None:
        message = str(buf)
        upper = message.upper()
        routine_markers = (
            "CONNECT",
            "CONNACK",
            "DISCONNECT",
            "PUBLISH",
            "PUBACK",
            "PINGREQ",
            "PINGRESP",
            "SUBSCRIBE",
            "SUBACK",
        )
        if any(marker in upper for marker in routine_markers):
            logger.debug("[MQTT] %s", message)
            return
        if level >= mqtt.MQTT_LOG_ERR:
            logger.warning("[MQTT] %s", message)
        elif level >= mqtt.MQTT_LOG_WARNING:
            logger.info("[MQTT] %s", message)
        else:
            logger.debug("[MQTT] %s", message)


def decode_json_payload(payload: bytes) -> dict[str, Any]:
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("MQTT payload must be a JSON object")
    return data
