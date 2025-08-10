import json, ssl, time, socket
from typing import Optional
import paho.mqtt.client as mqtt

class MqttClient:
    def __init__(self, host: str, port: int = 1883, username: str = "", password: str = "",
                 use_tls: bool = False, ca_certs: str | None = None, client_id: str | None = None,
                 connect_timeout: int = 10, max_retries: int = 20, retry_backoff_s: float = 0.5):

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id or "",
            protocol=mqtt.MQTTv311,          # << force MQTT 3.1.1
            transport="tcp",
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
        self.client.on_log = self._on_log

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
            print("[MQTT] Connected.")
        else:
            print(f"[MQTT] Connect failed rc={rc}")

    def _on_disconnect(self, client, userdata, rc, properties=None):
        print(f"[MQTT] Disconnected rc={rc}")

    def _on_log(self, client, userdata, level, buf):
        if level >= mqtt.MQTT_LOG_ERR:
            print(f"[MQTT] {buf}")
