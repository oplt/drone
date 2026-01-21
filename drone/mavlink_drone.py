import time
import threading
from dronekit import connect, VehicleMode, LocationGlobal, LocationGlobalRelative
from .models import Coordinate, Telemetry
from .drone_base import DroneClient
from utils.telemetry_publisher_sim import ArduPilotTelemetryPublisher
from config import setup_logging
import logging

setup_logging()


class MavlinkDrone(DroneClient):
    def __init__(self, connection_str: str, heartbeat_timeout: float):
        self.connection_str = connection_str
        self.vehicle = None
        self.heartbeat_timeout = heartbeat_timeout
        self.last_heartbeat = time.time()
        self.dead_mans_switch_active = False
        self.home_location = None
        self._heartbeat_thread = None
        self._running = False

    def connect(self) -> None:
        self.vehicle = connect(self.connection_str, wait_ready=True)

        # Wait until autopilot sets home_location (requires GPS fix; often set after arm, but we try early)
        logging.info("Waiting for home location...")
        tries = 0
        while not getattr(self.vehicle, "home_location", None) and tries < 30:
            time.sleep(0.5)  # Reduced sleep time for faster response
            tries += 1

        if self.vehicle.home_location:
            self.home_location = self.vehicle.home_location
        else:
            # Fallback: use current global frame as a provisional "home"
            loc = self.vehicle.location.global_frame
            self.home_location = loc

        # print(f"Home location set: {self.home_location}")
        logging.info(f"Home location set: {self.home_location}")

        # Start the dead man's switch monitoring for safety
        self.start_dead_mans_switch()

    '''SHOULD BE MODIFIED AND ADDED TO RASPBERRY PI ON DRONE'''
    def start_dead_mans_switch(self):
        """Start the dead man's switch monitoring thread"""
        self.dead_mans_switch_active = True
        self._running = True
        self.last_heartbeat = time.time()  # Reset heartbeat

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_monitor,
            daemon=True,
            name="DeadMansSwitch"
        )
        self._heartbeat_thread.start()
        logging.info("Dead man's switch activated")
        # print("Dead man's switch activated")

    # def send_heartbeat(self):
    #     """Call this method regularly from your main application to keep the drone active"""
    #     if self.dead_mans_switch_active:
    #         self.last_heartbeat = time.time()
    #         logging.info(f"Heartbeat sent at {self.last_heartbeat}")
    #         # print(f"Heartbeat sent at {self.last_heartbeat}")  # Uncomment for debugging

    '''SHOULD BE MODIFIED AND ADDED TO RASPBERRY PI ON DRONE'''
    def _heartbeat_monitor(self):
        """Background thread that monitors heartbeat and triggers emergency actions"""
        while self._running and self.vehicle:
            try:
                time_since_heartbeat = time.time() - self.last_heartbeat

                if time_since_heartbeat > self.heartbeat_timeout:
                    # print(f"⚠️  DEAD MAN'S SWITCH TRIGGERED! No heartbeat for {time_since_heartbeat:.1f}s")
                    logging.info(f"⚠️  DEAD MAN'S SWITCH TRIGGERED! No heartbeat for {time_since_heartbeat:.1f}s")
                    self._trigger_emergency_action()
                    break  # Exit the monitoring loop after triggering

                time.sleep(1.0)  # Check every second

            except Exception as e:
                # print(f"Error in dead man's switch monitor: {e}")
                logging.info(f"Error in dead man's switch monitor: {e}")
                # If we can't monitor properly, trigger emergency action to be safe
                self._trigger_emergency_action()
                break

    '''SHOULD BE MODIFIED AND ADDED TO RASPBERRY PI ON DRONE'''
    def _trigger_emergency_action(self):
        """Executed when dead man's switch is triggered"""
        try:
            if not self.vehicle:
                return

            # print("🚨 EXECUTING EMERGENCY PROTOCOL")
            logging.info("🚨 EXECUTING EMERGENCY PROTOCOL")

            # Option 1: Return to Launch (RTL) - Recommended
            # print("Setting mode to RTL (Return to Launch)")
            logging.info("Setting mode to RTL (Return to Launch)")
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

        except Exception as e:
            # print(f"❌ Critical error in emergency action: {e}")
            logging.info(f"❌ Critical error in emergency action: {e}")
            # Last resort - try to land
            try:
                if self.vehicle:
                    self.vehicle.mode = VehicleMode("LAND")
            except:
                pass

    def arm_and_takeoff(self, alt: float) -> None:
        while not self.vehicle.is_armable:
            time.sleep(0.5)  # Reduced sleep for faster response

        self.vehicle.mode = VehicleMode("GUIDED")
        self.vehicle.armed = True

        while not self.vehicle.armed:
            time.sleep(0.5)  # Reduced sleep for faster response

        self.vehicle.simple_takeoff(alt)

        while True:
            current_alt = self.vehicle.location.global_relative_frame.alt
            if current_alt >= alt * 0.95:
                break
            time.sleep(0.5)  # Reduced sleep for faster response and better cancellation support

    def goto(self, coord: Coordinate) -> None:
        # Send heartbeat before major operations
        # self.send_heartbeat()

        target = LocationGlobalRelative(coord.lat, coord.lon, coord.alt)
        self.vehicle.simple_goto(target)

    def set_mode(self, mode: str) -> None:
        # self.send_heartbeat()
        self.vehicle.mode = VehicleMode(mode)

    def get_telemetry(self) -> Telemetry:
        # Send heartbeat when getting telemetry (this happens regularly)
        # self.send_heartbeat()

        v = self.vehicle
        if v is None:
            raise RuntimeError("Vehicle not connected yet")

        loc = getattr(v, "location", None)
        rel = getattr(loc, "global_relative_frame", None)
        if rel is None:
            raise RuntimeError("Vehicle location not ready yet")
        bat = getattr(v, "battery", None)
        return Telemetry(
            lat=rel.lat,
            lon=rel.lon,
            alt=rel.alt,
            heading=v.heading,
            groundspeed=v.groundspeed,
            mode=v.mode.name,
            battery_voltage=getattr(bat, "voltage", None),
            battery_current=getattr(bat, "current", None),
            battery_remaining=getattr(bat, "level", None),
        )

    def follow_waypoints(self, path):
        for wp in path:
            self.goto(wp)

            # Wait for waypoint with reduced sleep for better responsiveness
            start_time = time.time()
            while time.time() - start_time < 30:  # 30 second timeout per waypoint
                # Check if we're close enough to the waypoint
                current = self.vehicle.location.global_relative_frame
                distance = self._distance_to_target(current, wp)

                if distance < 2.0:  # Within 2 meters
                    break

                time.sleep(0.5)  # Reduced sleep for faster waypoint detection

    def _distance_to_target(self, current_loc, target_coord):
        """Calculate distance to target coordinate"""
        from math import radians, sin, cos, sqrt, atan2

        # Haversine formula for distance
        R = 6371000  # Earth's radius in meters

        lat1, lon1 = radians(current_loc.lat), radians(current_loc.lon)
        lat2, lon2 = radians(target_coord.lat), radians(target_coord.lon)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))

        return R * c

    def land(self) -> None:
        # self.send_heartbeat()
        self.vehicle.mode = VehicleMode("LAND")


    def wait_until_disarmed(self, timeout_s: float = 900):
        """Block until vehicle.armed == False or timeout."""
        start = time.time()
        while self.vehicle and getattr(self.vehicle, "armed", False) and (time.time() - start) < timeout_s:
            time.sleep(0.5)  # Reduced sleep for faster response


    def stop_dead_mans_switch(self):
        """Safely disable the dead man's switch"""
        # print("Stopping dead man's switch...")
        logging.info("Stopping dead man's switch...")
        self._running = False
        self.dead_mans_switch_active = False

        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)

    def close(self) -> None:
        self.stop_dead_mans_switch()
        if self.vehicle:
            self.vehicle.close()


    def is_connected(self) -> bool:
        """Check if drone is connected and ready"""
        if not self.vehicle:
            return False

        try:
            # Check if vehicle object is still valid
            # Check basic attributes to ensure connection is alive
            if hasattr(self.vehicle, 'location'):
                # Try to get location as a test
                _ = self.vehicle.location.global_frame
                return True
            return False
        except:
            return False

    def get_connection_status(self) -> dict:
        """Get detailed connection status"""
        return {
            "connected": self.is_connected(),
            "vehicle_ready": self.vehicle is not None,
            "home_location_set": self.home_location is not None,
            "mode": self.vehicle.mode.name if self.vehicle else None,
            "armed": self.vehicle.armed if self.vehicle else False
        }


