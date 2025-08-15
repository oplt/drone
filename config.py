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
    drone_conn_mavproxy: str = os.getenv("DRONE_CONNECTION_STR_MAVPROXY", "tcp:127.0.0.1:5760")
    # If connecting to a networked drone:
    # "udp:192.168.0.10:14550" (IP/port from your drone's telemetry)

    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/drone_db")
    telem_log_interval_sec: float = float(os.getenv("TELEMETRY_LOG_INTERVAL_SEC", "2"))
    telemetry_topic: str = "ardupilot/telemetry"

    cam_source = os.getenv("CAM_SOURCE", "0")


    battery_capacity_wh: float = float(os.getenv("BATTERY_CAPACITY_WH", "77"))
    cruise_power_w: float = float(os.getenv("CRUISE_POWER_W", "180"))
    cruise_speed_mps: float = float(os.getenv("CRUISE_SPEED_MPS", "8"))
    energy_reserve_frac: float = float(os.getenv("ENERGY_RESERVE_FRAC", "0.2"))

    heartbeat_timeout : float = float(os.getenv("HEARTBEAT_TIMEOUT", "5"))

    ENFORCE_PREFLIGHT_RANGE = os.getenv("ENFORCE_PREFLIGHT_RANGE", "true").lower() in {"1","true","yes","on"}

settings = Settings()
