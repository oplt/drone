import time
import threading
from dronekit import connect, VehicleMode, LocationGlobal, LocationGlobalRelative

from .models import Coordinate, Telemetry
from .drone_base import DroneClient

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

        # Try to obtain a valid LocationGlobal for home
        start = time.time()
        timeout_s = 30
        while not self.vehicle.home_location and (time.time() - start) < timeout_s:
            # If GPS already has a global_frame, use that
            try:
                gf = self.vehicle.location.global_frame
                if gf and isinstance(gf, LocationGlobal):
                    self.vehicle.home_location = gf
            except Exception:
                pass
            print("Waiting for home location...")
            time.sleep(1)

        if not self.vehicle.home_location or not isinstance(self.vehicle.home_location, LocationGlobal):
            raise RuntimeError("Failed to set a LocationGlobal home_location (GPS lock / EKF?).")

        # Keep a copy on the class for convenience
        self.home_location = self.vehicle.home_location
        print(f"Home location set: lat={self.home_location.lat:.6f}, lon={self.home_location.lon:.6f}, alt={getattr(self.home_location,'alt',0)}")

        self.start_dead_mans_switch()

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
        print("Dead man's switch activated")

    def send_heartbeat(self):
        """Call this method regularly from your main application to keep the drone active"""
        if self.dead_mans_switch_active:
            self.last_heartbeat = time.time()
            # print(f"Heartbeat sent at {self.last_heartbeat}")  # Uncomment for debugging

    def _heartbeat_monitor(self):
        """Background thread that monitors heartbeat and triggers emergency actions"""
        while self._running and self.vehicle:
            try:
                time_since_heartbeat = time.time() - self.last_heartbeat

                if time_since_heartbeat > self.heartbeat_timeout:
                    print(f"⚠️  DEAD MAN'S SWITCH TRIGGERED! No heartbeat for {time_since_heartbeat:.1f}s")
                    self._trigger_emergency_action()
                    break  # Exit the monitoring loop after triggering

                time.sleep(1.0)  # Check every second

            except Exception as e:
                print(f"Error in dead man's switch monitor: {e}")
                # If we can't monitor properly, trigger emergency action to be safe
                self._trigger_emergency_action()
                break

    def _trigger_emergency_action(self):
        """Executed when dead man's switch is triggered"""
        try:
            if not self.vehicle:
                return

            print("🚨 EXECUTING EMERGENCY PROTOCOL")

            # Option 1: Return to Launch (RTL) - Recommended
            print("Setting mode to RTL (Return to Launch)")
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
            print(f"❌ Critical error in emergency action: {e}")
            # Last resort - try to land
            try:
                if self.vehicle:
                    self.vehicle.mode = VehicleMode("LAND")
            except:
                pass

    def arm_and_takeoff(self, alt: float) -> None:
        while not self.vehicle.is_armable:
            time.sleep(1)

        self.vehicle.mode = VehicleMode("GUIDED")
        self.vehicle.armed = True

        while not self.vehicle.armed:
            time.sleep(1)

        self.vehicle.simple_takeoff(alt)

        while True:
            # Send heartbeat during takeoff
            self.send_heartbeat()

            current_alt = self.vehicle.location.global_relative_frame.alt
            if current_alt >= alt * 0.95:
                break
            time.sleep(1)

    def goto(self, coord: Coordinate) -> None:
        # Send heartbeat before major operations
        self.send_heartbeat()

        target = LocationGlobalRelative(coord.lat, coord.lon, coord.alt)
        self.vehicle.simple_goto(target)

    def set_mode(self, mode: str) -> None:
        self.send_heartbeat()
        self.vehicle.mode = VehicleMode(mode)

    def get_telemetry(self) -> Telemetry:
        # Send heartbeat when getting telemetry (this happens regularly)
        self.send_heartbeat()

        v = self.vehicle
        loc = v.location.global_relative_frame
        bat = getattr(v, "battery", None)
        return Telemetry(
            lat=loc.lat, lon=loc.lon, alt=loc.alt,
            heading=v.heading, groundspeed=v.groundspeed,
            armed=v.armed, mode=v.mode.name,
            battery_voltage=getattr(bat, "voltage", None),
            battery_current=getattr(bat, "current", None),
            battery_level=getattr(bat, "level", None),
        )

    def follow_waypoints(self, path):
        for wp in path:
            self.send_heartbeat()  # Heartbeat before each waypoint
            self.goto(wp)

            # Wait for waypoint with heartbeat
            start_time = time.time()
            while time.time() - start_time < 30:  # 30 second timeout per waypoint
                self.send_heartbeat()

                # Check if we're close enough to the waypoint
                current = self.vehicle.location.global_relative_frame
                distance = self._distance_to_target(current, wp)

                if distance < 2.0:  # Within 2 meters
                    break

                time.sleep(1)

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
        self.send_heartbeat()
        self.vehicle.mode = VehicleMode("LAND")

    def stop_dead_mans_switch(self):
        """Safely disable the dead man's switch"""
        print("Stopping dead man's switch...")
        self._running = False
        self.dead_mans_switch_active = False

        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)

    def close(self) -> None:
        self.stop_dead_mans_switch()
        if self.vehicle:
            self.vehicle.close()


