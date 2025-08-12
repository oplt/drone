from pymavlink import mavutil
import paho.mqtt.client as mqtt
import json
import time
from config import settings
from pymavlink.dialects.v20 import ardupilotmega as mavlink


# MQTT Broker Settings
MQTT_BROKER = settings.mqtt_broker
MQTT_PORT = settings.mqtt_port
MQTT_TOPIC = "ardupilot/telemetry"

# Connect to MAVProxy (SITL)
mav_conn = mavutil.mavlink_connection(settings.drone_conn)

# MQTT Client Setup
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)  # <-- Fixes the deprecation warning
mqtt_client.connect(MQTT_BROKER, MQTT_PORT)

print("Forwarding MAVLink messages to MQTT...")

while True:
    msg = mav_conn.recv_match(blocking=True,
                              type=['HEARTBEAT',
                                    'GLOBAL_POSITION_INT',
                                    'VFR_HUD',
                                    'BATTERY_STATUS',
                                    'ATTITUDE',
                                    'SYS_STATUS',
                                    'GPS_RAW_INT',
                                    'SYSTEM_TIME',
                                    'TIMESYNC',
                                    'WIND_COV',
                                    'DISTANCE_SENSOR',
                                    ]) # ,  # <-- Filter specific messages
    if msg:
        # Convert MAVLink message to JSON
        msg_dict = msg.to_dict()
        mqtt_client.publish(MQTT_TOPIC, json.dumps(msg_dict))
        print(f"Published: {msg.get_type()}")
    # time.sleep(5)