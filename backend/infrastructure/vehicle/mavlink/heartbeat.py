from __future__ import annotations

import logging
import threading

from dronekit import VehicleMode

from backend.infrastructure.vehicle.mavlink._client_refs import client_module
from backend.infrastructure.vehicle.mavlink.config import logger


class MavlinkHeartbeatMixin:
    """Dead man's switch monitoring."""

    def start_dead_mans_switch(self):
        """Start the dead man's switch monitoring thread"""
        self.dead_mans_switch_active = True
        self.dead_mans_switch_triggered = False
        self._running = True
        self.last_heartbeat = client_module().time.time()  # Reset heartbeat

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_monitor, daemon=True, name="DeadMansSwitch"
        )
        self._heartbeat_thread.start()
        logger.info("Dead man's switch activated")
        # print("Dead man's switch activated")

    # def send_heartbeat(self):
    #     """Call this method regularly from your main application to keep the drone active"""
    #     if self.dead_mans_switch_active:
    #         self.last_heartbeat = client_module().time.time()
    #         logger.info(f"Heartbeat sent at {self.last_heartbeat}")
    #         # print(f"Heartbeat sent at {self.last_heartbeat}")  # Uncomment for debugging

    """SHOULD BE MODIFIED AND ADDED TO RASPBERRY PI ON DRONE"""

    def _heartbeat_monitor(self):
        """Background thread that monitors heartbeat and triggers emergency actions"""
        while self._running and self.vehicle:
            try:
                time_since_heartbeat = client_module().time.time() - self.last_heartbeat

                if time_since_heartbeat > self.heartbeat_timeout:
                    # print(f"⚠️  DEAD MAN'S SWITCH TRIGGERED! No heartbeat for {time_since_heartbeat:.1f}s")
                    logger.info(
                        f"⚠️  DEAD MAN'S SWITCH TRIGGERED! No heartbeat for {time_since_heartbeat:.1f}s"
                    )
                    self._trigger_emergency_action()
                    break  # Exit the monitoring loop after triggering

                client_module().time.sleep(1.0)  # Check every second

            except Exception as e:
                # print(f"Error in dead man's switch monitor: {e}")
                logger.info(f"Error in dead man's switch monitor: {e}")
                # If we can't monitor properly, trigger emergency action to be safe
                self._trigger_emergency_action()
                break

    """SHOULD BE MODIFIED AND ADDED TO RASPBERRY PI ON DRONE"""

    def _trigger_emergency_action(self):
        """Executed when dead man's switch is triggered"""
        try:
            if not self.vehicle:
                return

            # print("🚨 EXECUTING EMERGENCY PROTOCOL")
            logger.info("🚨 EXECUTING EMERGENCY PROTOCOL")

            # Option 1: Return to Launch (RTL) - Recommended
            # print("Setting mode to RTL (Return to Launch)")
            logger.info("Setting mode to RTL (Return to Launch)")
            self.vehicle.mode = VehicleMode("RTL")

            # Option 2: Alternative - Land immediately at current location
            # print("Emergency landing at current location")
            # self.vehicle.mode = VehicleMode("LAND")

            # Option 3: Advanced - Go to a specific safe location first, then land
            # if self.home_location:
            #     safe_location = LocationGlobalRelative(
            #         self.home_location.lat,
            #         self.home_location.lon,
            #         30  # 30m altitude
            #     )
            #     self.vehicle.simple_goto(safe_location)
            #     time.sleep(5)  # Give it time to start moving
            #     self.vehicle.mode = VehicleMode("LAND")

            self.dead_mans_switch_active = False  # Disable further monitoring
            self.dead_mans_switch_triggered = True

        except Exception as e:
            # print(f"❌ Critical error in emergency action: {e}")
            logger.info(f"❌ Critical error in emergency action: {e}")
            # Last resort - try to land
            try:
                if self.vehicle:
                    self.vehicle.mode = VehicleMode("LAND")
            except:
                pass

