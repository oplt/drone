"""
Drone Command Handler
Handles commands from Flask dashboard and sends them via MQTT
"""

import paho.mqtt.client as mqtt
from config import settings
import logging
import json
from typing import Optional


class DroneCommandHandler:
    """Handles drone commands via MQTT"""

    def __init__(self):
        self.mqtt_client = None
        self.connected = False

    def connect(self):
        """Connect to MQTT broker"""
        try:
            self.mqtt_client = mqtt.Client(client_id="flask_dashboard")

            if settings.mqtt_user and settings.mqtt_pass:
                self.mqtt_client.username_pw_set(settings.mqtt_user, settings.mqtt_pass)

            self.mqtt_client.on_connect = self._on_connect
            self.mqtt_client.on_disconnect = self._on_disconnect

            self.mqtt_client.connect(settings.mqtt_broker, settings.mqtt_port, 60)
            self.mqtt_client.loop_start()
            logging.info(
                f"Command handler connected to MQTT broker at {settings.mqtt_broker}:{settings.mqtt_port}"
            )
        except Exception as e:
            logging.error(f"Failed to connect command handler to MQTT: {e}")
            self.connected = False

    def _on_connect(self, _client, _userdata, _flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            self.connected = True
            logging.info("Command handler MQTT connection established")
        else:
            self.connected = False
            logging.error(f"Command handler MQTT connection failed with code {rc}")

    def _on_disconnect(self, _client, _userdata, rc):
        """MQTT disconnection callback"""
        self.connected = False
        logging.warning("Command handler MQTT disconnected")

    def send_command(self, command: str, params: Optional[dict] = None) -> bool:
        """
        Send command to drone via MQTT

        Args:
            command: Command name (ARM, DISARM, TAKEOFF, LAND, RTL, HOLD, SET_MODE, etc.)
            params: Optional parameters for the command

        Returns:
            True if command was sent successfully, False otherwise
        """
        if not self.connected or not self.mqtt_client:
            logging.warning("Command handler not connected to MQTT")
            return False

        try:
            payload = {
                "command": command,
                "timestamp": None,  # Will be set by receiver
            }

            if params:
                payload.update(params)

            topic = f"drone/commands/{command.lower()}"
            result = self.mqtt_client.publish(topic, json.dumps(payload), qos=1)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logging.info(f"Command '{command}' sent to topic '{topic}'")
                return True
            else:
                logging.error(
                    f"Failed to send command '{command}': MQTT error {result.rc}"
                )
                return False

        except Exception as e:
            logging.error(f"Error sending command '{command}': {e}")
            return False

    def disconnect(self):
        """Disconnect from MQTT broker"""
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.connected = False


# Global command handler instance
_command_handler: Optional[DroneCommandHandler] = None


def get_command_handler() -> DroneCommandHandler:
    """Get or create command handler instance"""
    global _command_handler
    if _command_handler is None:
        _command_handler = DroneCommandHandler()
        _command_handler.connect()
    return _command_handler
