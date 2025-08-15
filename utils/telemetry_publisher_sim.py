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
                    ])


class ArduPilotTelemetryPublisher:
    def __init__(self, mqtt_client=None, mqtt_topic=None, drone_connection=None):
        # MQTT Broker Settings
        # self.mqtt_broker = mqtt_broker or settings.mqtt_broker
        # self.mqtt_port = mqtt_port or settings.mqtt_port
        self.mqtt_topic = settings.telemetry_topic

        # Drone connection
        self.drone_conn_str = settings.drone_conn_mavproxy
        # self.drone_conn_str = settings.drone_conn
        self.mav_conn = None
        self.mqtt_client = mqtt_client

        # Control flags
        self.is_running = False
        self.publisher_thread = None

        # Message types to filter
        self.message_types = [
            'GLOBAL_POSITION_INT',
            'VFR_HUD',
            'PLANE_MODE',
            'BATTERY_STATUS',
            'SYS_STATUS',

        ]

    def connect_mavlink(self):
        """Establish MAVLink connection"""
        try:
            self.mav_conn = mavutil.mavlink_connection(self.drone_conn_str)
            logging.info(f"Connected to MAVLink: {self.drone_conn_str}")
            return True
        except Exception as e:
            logging.info(f"Failed to connect to MAVLink: {e}")
            return False



    def start(self):
        """Start the telemetry publisher"""
        if self.is_running:
            logging.info("Publisher is already running")
            return False

        # Connect to MAVLink and MQTT
        if not self.connect_mavlink():
            return False

        # Start publishing in a separate thread
        self.is_running = True
        self.publisher_thread = threading.Thread(target=self._publish_loop, daemon=True)
        self.publisher_thread.start()

        logging.info("ArduPilot Telemetry Publisher started")
        return True

    def stop(self):
        """Stop the telemetry publisher"""
        if not self.is_running:
            logging.info("Publisher is not running")
            return

        logging.info("Stopping ArduPilot Telemetry Publisher...")
        self.is_running = False

        # Wait for thread to finish
        if self.publisher_thread and self.publisher_thread.is_alive():
            self.publisher_thread.join(timeout=5)

        # Close connections
        if self.mqtt_client:
            self.mqtt_client.close()

        if self.mav_conn:
            self.mav_conn.close()

        logging.info("ArduPilot Telemetry Publisher stopped")

    def _publish_loop(self):
        """Main publishing loop (runs in separate thread)"""
        logging.info("Starting MAVLink to MQTT forwarding...")

        while self.is_running:
            try:
                msg = self.mav_conn.recv_match(
                    blocking=False,
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
                    # logging.info(f"Published: {msg.get_type()}") # Uncomment for debugging

            except Exception as e:
                if self.is_running:  # Only print error if we're supposed to be running
                    logging.info(f"Error in publish loop: {e}")
                    time.sleep(1)  # Brief pause before retrying

    def is_alive(self):
        """Check if the publisher is running"""
        return self.is_running and (self.publisher_thread and self.publisher_thread.is_alive())

    def set_message_types(self, message_types):
        """Update the message types to filter"""
        self.message_types = message_types
        logging.info(f"Updated message types: {self.message_types}")