# DELETE THIS FILE AFTER DRONE CONNECTION IS ESTABLISHED. THIS FILE PUBLISHES TELEMETRY MESSAGES TO BROKER SINCE ARDUPILOT SITL DOESNT DO THAT

from pymavlink import mavutil
import json
import time
import threading
from backend.config import settings
import logging
from backend.messaging.opcua import DroneOpcUaServer
import asyncio

logger = logging.getLogger(__name__)


class ArduPilotTelemetryPublisher:
    def __init__(
        self,
        mqtt_client=None,
        mqtt_topic=None,
        drone_connection=None,
        opcua_server=None,
        opcua_event_loop=None,
    ):
        self.mqtt_topic = settings.telemetry_topic
        self.mqtt_client = mqtt_client
        self._owns_mqtt_client = mqtt_client is None

        self.drone_conn_str = settings.drone_conn_mavproxy
        self.mav_conn = None

        # OPC UA Server
        self.opcua_server = opcua_server or DroneOpcUaServer()
        # If the caller supplied an event loop, we will reuse it (shared server)
        # Otherwise, we'll create our own loop and own the server lifecycle
        self.opcua_server_loop = opcua_event_loop or asyncio.new_event_loop()
        self._owns_opcua_server = opcua_server is None
        self._owns_opcua_loop = opcua_event_loop is None
        self.opcua_server_thread = None

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
            logger.info(f"Connected to MAVLink: {self.drone_conn_str}")
            return True
        except Exception as e:
            logger.info(f"Failed to connect to MAVLink: {e}")
            return False

    def start_opcua_server(self):
        """Start OPC UA server in a separate thread"""

        def run_server():
            asyncio.set_event_loop(self.opcua_server_loop)
            # Start the server, then keep the loop running so we can schedule updates
            self.opcua_server_loop.run_until_complete(self.opcua_server.start())
            # Keep the event loop alive to process scheduled coroutines
            try:
                self.opcua_server_loop.run_forever()
            finally:
                # Ensure loop is closed when stopped
                self.opcua_server_loop.close()
            self.opcua_server_thread = threading.current_thread()

        threading.Thread(target=run_server, daemon=True).start()
        logger.info("OPC UA Server thread launched")

    async def update_opcua_variables(self, msg_dict):
        """Update OPC UA variables based on MAVLink message"""
        msg_type = msg_dict.get("mavpackettype")
        logger.info(f"Processing MAVLink message type: {msg_type}")
        logging.debug(f"Full message content: {msg_dict}")

        try:
            if msg_type == "GLOBAL_POSITION_INT":
                lat = float(msg_dict.get("lat", 0) / 1e7)  # Convert to degrees
                lon = float(msg_dict.get("lon", 0) / 1e7)  # Convert to degrees
                alt = float(msg_dict.get("alt", 0) / 1e3)  # Convert to meters

                logger.info(f"Updating position - Lat: {lat}, Lon: {lon}, Alt: {alt}")
                await self.opcua_server.vars["lat"].write_value(lat)
                await self.opcua_server.vars["lon"].write_value(lon)
                await self.opcua_server.vars["alt"].write_value(alt)

            elif msg_type == "VFR_HUD":
                groundspeed = float(msg_dict.get("groundspeed", 0))
                heading = float(msg_dict.get("heading", 0))

                logger.info(f"Updating HUD - Speed: {groundspeed}, Heading: {heading}")
                await self.opcua_server.vars["groundspeed"].write_value(groundspeed)
                await self.opcua_server.vars["heading"].write_value(heading)

            elif msg_type == "BATTERY_STATUS":
                voltages = msg_dict.get("voltages", [0])
                voltage = float(voltages[0] / 1000) if voltages else 0.0  # mV to V
                current = float(msg_dict.get("current_battery", 0) / 100)  # cA to A
                remaining = int(msg_dict.get("battery_remaining", -1))

                logger.info(
                    f"Updating Battery - Voltage: {voltage}, Current: {current}, Remaining: {remaining}%"
                )
                await self.opcua_server.vars["battery_voltage"].write_value(voltage)
                await self.opcua_server.vars["battery_current"].write_value(current)
                await self.opcua_server.vars["battery_remaining"].write_value(remaining)

            elif msg_type == "SYSTEM_TIME":
                system_time = float(
                    msg_dict.get("time_unix_usec", 0) / 1e6
                )  # Convert microseconds to seconds
                logger.info(f"Updating System Time: {system_time}")
                await self.opcua_server.vars["system_time"].write_value(system_time)

            elif msg_type == "HEARTBEAT":
                # Convert custom mode number to mode name
                mode_mapping = {
                    0: "STABILIZE",
                    1: "ACRO",
                    2: "ALT_HOLD",
                    3: "AUTO",
                    4: "GUIDED",
                    5: "LOITER",
                    6: "RTL",
                    7: "CIRCLE",
                    8: "POSITION",
                    9: "LAND",
                    10: "OF_LOITER",
                    11: "DRIFT",
                    13: "SPORT",
                    14: "FLIP",
                    15: "AUTOTUNE",
                    16: "POSHOLD",
                    17: "BRAKE",
                    18: "THROW",
                    19: "AVOID_ADSB",
                    20: "GUIDED_NOGPS",
                    21: "SMART_RTL",
                }
                custom_mode = msg_dict.get("custom_mode", 0)
                mode = mode_mapping.get(custom_mode, "UNKNOWN")

                logger.info(f"Updating Mode: {mode}")
                await self.opcua_server.vars["mode"].write_value(mode)

        except Exception as e:
            logger.error(
                f"Error updating OPC UA variables for {msg_type}: {e}", exc_info=True
            )

    def start(self):
        """Start the telemetry publisher"""
        if self.is_running:
            logger.info("Publisher is already running")
            return False

        # Connect to MAVLink and MQTT
        if not self.connect_mavlink():
            return False

        # Start OPC UA server if we own it; otherwise assume it is already started
        if self._owns_opcua_server:
            self.start_opcua_server()
        else:
            # Validate that an event loop was provided for scheduling updates
            if self.opcua_server_loop is None:
                logger.error(
                    "Shared OPC UA server provided without an event loop. Cannot schedule updates."
                )
                return False

        # Start publishing in a separate thread
        self.is_running = True
        self.publisher_thread = threading.Thread(target=self._publish_loop, daemon=True)
        self.publisher_thread.start()

        logger.info("ArduPilot Telemetry Publisher started")
        return True

    def stop(self):
        """Stop the telemetry publisher"""
        if not self.is_running:
            logger.info("Publisher is not running")
            return

        logger.info("Stopping ArduPilot Telemetry Publisher...")
        self.is_running = False

        # Wait for threads to finish
        if self.publisher_thread and self.publisher_thread.is_alive():
            self.publisher_thread.join(timeout=5)

        # Stop OPC UA server only if we own it
        if (
            self._owns_opcua_server
            and self.opcua_server_loop
            and self.opcua_server_loop.is_running()
        ):
            try:
                asyncio.run_coroutine_threadsafe(
                    self.opcua_server.stop(), self.opcua_server_loop
                ).result()
            except Exception as e:
                logger.error(f"Error stopping OPC UA server: {e}")
            finally:
                self.opcua_server_loop.call_soon_threadsafe(self.opcua_server_loop.stop)

        # Close connections
        # Only close MQTT if we created/own it
        if self._owns_mqtt_client and self.mqtt_client:
            self.mqtt_client.close()

        if self.mav_conn:
            self.mav_conn.close()

        logger.info("ArduPilot Telemetry Publisher stopped")

    def _publish_loop(self):
        """Main publishing loop (runs in separate thread)"""
        logger.info("Starting MAVLink to MQTT and OPC UA forwarding...")

        while self.is_running:
            try:
                msg = self.mav_conn.recv_match(
                    blocking=False, timeout=1.0, type=self.message_types
                )

                if msg and self.is_running:
                    # Convert MAVLink message to JSON
                    msg_dict = msg.to_dict()
                    msg_dict["timestamp"] = time.time()

                    # Publish to MQTT
                    if self.mqtt_client:
                        self.mqtt_client.publish(self.mqtt_topic, json.dumps(msg_dict))

                    # Update OPC UA variables
                    if self.opcua_server_loop:
                        try:
                            asyncio.run_coroutine_threadsafe(
                                self.update_opcua_variables(msg_dict),
                                self.opcua_server_loop,
                            )
                        except Exception as e:
                            logger.error(f"Failed to schedule OPC UA update: {e}")

            except Exception as e:
                if self.is_running:
                    logger.error(f"Error in publish loop: {e}")
                    time.sleep(1)

    def is_alive(self):
        """Check if the publisher is running"""
        return self.is_running and (
            self.publisher_thread and self.publisher_thread.is_alive()
        )

    def set_message_types(self, message_types):
        """Update the message types to filter"""
        self.message_types = message_types
        logger.info(f"Updated message types: {self.message_types}")
