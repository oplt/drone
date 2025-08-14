# DELETE THIS FILE AFTER DRONE CONNECTION IS ESTABLISHED. THIS FILE PUBLISHES TELEMETRY MESSAGES TO BROKER SINCE ARDUPILOT SITL DOESNT DO THAT

from pymavlink import mavutil
import paho.mqtt.client as mqtt
import json
import time
import threading
from config import settings
# from pymavlink.dialects.v20 import ardupilotmega as mavlink
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("drone.log"),
        logging.StreamHandler()  # still print to console
    ]
)


class ArduPilotTelemetryPublisher:
    def __init__(self, mqtt_broker=None, mqtt_port=None, mqtt_topic=None, drone_connection=None):
        # MQTT Broker Settings
        self.mqtt_broker = mqtt_broker or settings.mqtt_broker
        self.mqtt_port = mqtt_port or settings.mqtt_port
        self.mqtt_topic = mqtt_topic or "ardupilot/telemetry"

        # Drone connection
        self.drone_conn_str = drone_connection or settings.drone_conn
        self.mav_conn = None
        self.mqtt_client = None

        # Control flags
        self.is_running = False
        self.publisher_thread = None

        # Message types to filter
        self.message_types = [
            'HEARTBEAT',
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
        ]

    def connect_mavlink(self):
        """Establish MAVLink connection"""
        try:
            self.mav_conn = mavutil.mavlink_connection(self.drone_conn_str)
            # print(f"Connected to MAVLink: {self.drone_conn_str}")
            logging.info(f"Connected to MAVLink: {self.drone_conn_str}")
            return True
        except Exception as e:
            # print(f"Failed to connect to MAVLink: {e}")
            logging.info(f"Failed to connect to MAVLink: {e}")
            return False

    def connect_mqtt(self):
        """Establish MQTT connection"""
        try:
            self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port)
            # print(f"Connected to MQTT broker: {self.mqtt_broker}:{self.mqtt_port}")
            logging.info("Connected to MQTT broker: {self.mqtt_broker}:{self.mqtt_port}")
            return True
        except Exception as e:
            # print(f"Failed to connect to MQTT broker: {e}")
            logging.info(f"Failed to connect to MQTT broker: {e}")
            return False

    def _publish_loop(self):
        """Main publishing loop (runs in separate thread)"""
        # print("Starting MAVLink to MQTT forwarding...")
        logging.info("Starting MAVLink to MQTT forwarding...")

        while self.is_running:
            try:
                msg = self.mav_conn.recv_match(
                    blocking=True,
                    timeout=1.0,  # Add timeout to allow checking is_running flag
                    type=self.message_types
                )

                if msg and self.is_running:
                    # Convert MAVLink message to JSON
                    msg_dict = msg.to_dict()

                    # Add timestamp if not present
                    if 'timestamp' not in msg_dict:
                        msg_dict['timestamp'] = time.time()

                    # Publish to MQTT
                    self.mqtt_client.publish(self.mqtt_topic, json.dumps(msg_dict))
                    # print(f"Published: {msg.get_type()}")
                    logging.info(f"Published: {msg.get_type()}")

            except Exception as e:
                if self.is_running:  # Only print error if we're supposed to be running
                    # print(f"Error in publish loop: {e}")
                    logging.info(f"Error in publish loop: {e}")
                    time.sleep(1)  # Brief pause before retrying

    def start(self):
        """Start the telemetry publisher"""
        if self.is_running:
            # print("Publisher is already running")
            logging.info("Publisher is already running")
            return False

        # Connect to MAVLink and MQTT
        if not self.connect_mavlink():
            return False

        if not self.connect_mqtt():
            return False

        # Start publishing in a separate thread
        self.is_running = True
        self.publisher_thread = threading.Thread(target=self._publish_loop, daemon=True)
        self.publisher_thread.start()

        # print("ArduPilot Telemetry Publisher started")
        logging.info("ArduPilot Telemetry Publisher started")
        return True

    def stop(self):
        """Stop the telemetry publisher"""
        if not self.is_running:
            # print("Publisher is not running")
            logging.info("Publisher is not running")
            return

        # print("Stopping ArduPilot Telemetry Publisher...")
        logging.info("Stopping ArduPilot Telemetry Publisher...")
        self.is_running = False

        # Wait for thread to finish
        if self.publisher_thread and self.publisher_thread.is_alive():
            self.publisher_thread.join(timeout=5)

        # Close connections
        if self.mqtt_client:
            self.mqtt_client.disconnect()

        if self.mav_conn:
            self.mav_conn.close()

        # print("ArduPilot Telemetry Publisher stopped")
        logging.info("ArduPilot Telemetry Publisher stopped")

    def is_alive(self):
        """Check if the publisher is running"""
        return self.is_running and (self.publisher_thread and self.publisher_thread.is_alive())

    def set_message_types(self, message_types):
        """Update the message types to filter"""
        self.message_types = message_types
        # print(f"Updated message types: {self.message_types}")
        logging.info(f"Updated message types: {self.message_types}")


# Example usage
# if __name__ == "__main__":
#     publisher = ArduPilotTelemetryPublisher()
#
#     try:
#         if publisher.start():
#             # Keep the main thread alive
#             while True:
#                 time.sleep(1)
#                 if not publisher.is_alive():
#                     print("Publisher thread died, restarting...")
#                     publisher.stop()
#                     time.sleep(2)
#                     publisher.start()
#     except KeyboardInterrupt:
#         print("\nShutting down...")
#         publisher.stop()


# # MQTT Broker Settings
# MQTT_BROKER = settings.mqtt_broker
# MQTT_PORT = settings.mqtt_port
# MQTT_TOPIC = "ardupilot/telemetry"
#
# # Connect to MAVProxy (SITL)
# mav_conn = mavutil.mavlink_connection(settings.drone_conn)
#
# # MQTT Client Setup
# mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)  # <-- Fixes the deprecation warning
# mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
#
# print("Forwarding MAVLink messages to MQTT...")
#
# while True:
#     msg = mav_conn.recv_match(blocking=True,
#                               type=['HEARTBEAT',
#                                     'GLOBAL_POSITION_INT',
#                                     'VFR_HUD',
#                                     'BATTERY_STATUS',
#                                     'ATTITUDE',
#                                     'SYS_STATUS',
#                                     'GPS_RAW_INT',
#                                     'SYSTEM_TIME',
#                                     'TIMESYNC',
#                                     'WIND_COV',
#                                     'DISTANCE_SENSOR',
#                                     ]) # ,  # <-- Filter specific messages
#     if msg:
#         # Convert MAVLink message to JSON
#         msg_dict = msg.to_dict()
#         mqtt_client.publish(MQTT_TOPIC, json.dumps(msg_dict))
#         print(f"Published: {msg.get_type()}")
#     # time.sleep(5)