from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()

@dataclass
class Settings:
    google_maps_key: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")
    llm_api_base: str = os.getenv("LLM_API_BASE", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "")

    mqtt_broker: str = os.getenv("MQTT_BROKER", "localhost")
    mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
    mqtt_user: str = os.getenv("MQTT_USER", "")
    mqtt_pass: str = os.getenv("MQTT_PASS", "")
    opcua_endpoint: str = os.getenv("OPCUA_ENDPOINT", "opc.tcp://0.0.0.0:4840/drone")
    drone_conn: str = os.getenv("DRONE_CONNECTION_STR", "tcp:127.0.0.1:5760")
    # If connecting to a networked drone:
    # "udp:192.168.0.10:14550" (IP/port from your drone's telemetry)

    cam_source = os.getenv("CAM_SOURCE", "0")

settings = Settings()
