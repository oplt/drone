# DELETE THIS FILE AFTER DRONE CONNECTION IS ESTABLISHED. THIS FILE PUBLISHES TELEMETRY MESSAGES TO BROKER SINCE ARDUPILOT SITL DOESNT DO THAT

from pymavlink import mavutil
import paho.mqtt.client as mqtt
import json
import time
import threading
from config import settings, setup_logging
import logging
from messaging.opcua import DroneOpcUaServer
import asyncio

class ArduPilotTelemetryPublisher:
    def __init__(self, mqtt_client=None, mqtt_topic=None, drone_connection=None):
        self.mqtt_topic = settings.telemetry_topic
        self.mqtt_client = mqtt_client

        self.drone_conn_str = settings.drone_conn_mavproxy
        self.mav_conn = None

        # OPC UA Server
        self.opcua_server = DroneOpcUaServer()
        self.opcua_server_loop = asyncio.new_event_loop()
        self.opcua_server_thread = None

        # Control flags
        self.is_running = False
        self.publisher_thread = None

        # Message types to filter
        self.message_types = [
            'GLOBAL_POSITION_INT',
            'VFR_HUD',
            'BATTERY_STATUS',
            'SYS_STATUS',
            'GPS_RAW_INT',
            'ATTITUDE'
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

    def start_opcua_server(self):
        """Start OPC UA server in a separate thread"""
        def run_server():
            asyncio.set_event_loop(self.opcua_server_loop)
            self.opcua_server_loop.run_until_complete(self.opcua_server.start())
            self.opcua_server_thread = threading.current_thread()

        threading.Thread(target=run_server, daemon=True).start()
        logging.info("OPC UA Server started")

    async def update_opcua_variables(self, msg_dict):
        """Update OPC UA variables based on MAVLink message"""
        msg_type = msg_dict.get('mavpackettype')

        try:
            if msg_type == 'GLOBAL_POSITION_INT':
                lat = msg_dict.get('lat', 0) / 1e7  # Convert to degrees
                lon = msg_dict.get('lon', 0) / 1e7  # Convert to degrees
                alt = msg_dict.get('alt', 0) / 1e3  # Convert to meters
                relative_alt = msg_dict.get('relative_alt', 0) / 1e3  # Convert to meters
                hdg = msg_dict.get('hdg', 0) / 100  # Convert to degrees

                await self.opcua_server.vars["Lat"].write_value(lat)
                await self.opcua_server.vars["Lon"].write_value(lon)
                await self.opcua_server.vars["Alt"].write_value(alt)
                await self.opcua_server.vars["Heading"].write_value(hdg)

            elif msg_type == 'GPS_RAW_INT':
                # Use GPS_RAW_INT as fallback if GLOBAL_POSITION_INT not available
                lat = msg_dict.get('lat', 0) / 1e7  # Convert to degrees
                lon = msg_dict.get('lon', 0) / 1e7  # Convert to degrees
                alt = msg_dict.get('alt', 0) / 1e3  # Convert to meters

                await self.opcua_server.vars["Lat"].write_value(lat)
                await self.opcua_server.vars["Lon"].write_value(lon)
                await self.opcua_server.vars["Alt"].write_value(alt)

            elif msg_type == 'VFR_HUD':
                groundspeed = msg_dict.get('groundspeed', 0)
                heading = msg_dict.get('heading', 0)
                alt = msg_dict.get('alt', 0)

                await self.opcua_server.vars["Groundspeed"].write_value(groundspeed)
                await self.opcua_server.vars["Heading"].write_value(heading)
                await self.opcua_server.vars["Alt"].write_value(alt)

            elif msg_type in ['BATTERY_STATUS', 'SYS_STATUS']:
                # Handle both battery message types
                if msg_type == 'BATTERY_STATUS':
                    voltage = msg_dict.get('voltages', [0])[0] / 1000  # mV to V
                    current = msg_dict.get('current_battery', 0) / 100  # cA to A
                    remaining = msg_dict.get('battery_remaining', -1)
                else:  # SYS_STATUS
                    voltage = msg_dict.get('voltage_battery', 0) / 1000  # mV to V
                    current = msg_dict.get('current_battery', 0) / 100  # cA to A
                    remaining = msg_dict.get('battery_remaining', -1)

                await self.opcua_server.vars["battery_voltage"].write_value(voltage)
                await self.opcua_server.vars["battery_current"].write_value(current)
                await self.opcua_server.vars["battery_remaining"].write_value(remaining)

        except Exception as e:
            logging.error(f"Error updating OPC UA variables: {e}")

    def start(self):
        """Start the telemetry publisher"""
        if self.is_running:
            logging.info("Publisher is already running")
            return False

        # Connect to MAVLink and MQTT
        if not self.connect_mavlink():
            return False

        # Start OPC UA server
        self.start_opcua_server()

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

        # Wait for threads to finish
        if self.publisher_thread and self.publisher_thread.is_alive():
            self.publisher_thread.join(timeout=5)

        # Stop OPC UA server
        if self.opcua_server_loop.is_running():
            asyncio.run_coroutine_threadsafe(self.opcua_server.stop(), self.opcua_server_loop).result()
            self.opcua_server_loop.stop()

        # Close connections
        if self.mqtt_client:
            self.mqtt_client.close()

        if self.mav_conn:
            self.mav_conn.close()

        logging.info("ArduPilot Telemetry Publisher stopped")

    def _publish_loop(self):
        """Main publishing loop (runs in separate thread)"""
        logging.info("Starting MAVLink to MQTT and OPC UA forwarding...")

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
                    msg_dict['timestamp'] = time.time()

                    # Publish to MQTT
                    if self.mqtt_client:
                        self.mqtt_client.publish(self.mqtt_topic, json.dumps(msg_dict))

                    # Update OPC UA variables
                    if self.opcua_server_loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self.update_opcua_variables(msg_dict),
                            self.opcua_server_loop
                        )

            except Exception as e:
                if self.is_running:
                    logging.error(f"Error in publish loop: {e}")
                    time.sleep(1)

    def is_alive(self):
        """Check if the publisher is running"""
        return self.is_running and (self.publisher_thread and self.publisher_thread.is_alive())

    def set_message_types(self, message_types):
        """Update the message types to filter"""
        self.message_types = message_types
        logging.info(f"Updated message types: {self.message_types}")