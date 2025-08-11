# SITL-Compatible MavlinkDrone with Dead Man's Switch
import time
import threading
from dronekit import connect, VehicleMode, LocationGlobalRelative
from drone.models import Coordinate, Telemetry
from drone.drone_base import DroneClient
import math

class SITLCompatibleDrone(DroneClient):
    def __init__(self, connection_str: str = "tcp:127.0.0.1:5762", heartbeat_timeout: float = 10.0):
        self.connection_str = connection_str
        self.vehicle = None
        self.heartbeat_timeout = heartbeat_timeout
        self.last_heartbeat = time.time()
        self.dead_mans_switch_active = False
        self.home_location = None
        self._heartbeat_thread = None
        self._running = False

    def connect(self) -> None:
        """Connect to SITL with proper error handling and retries"""
        print(f"Connecting to SITL at {self.connection_str}...")

        try:
            # Connect with SITL-friendly parameters
            self.vehicle = connect(
                self.connection_str,
                wait_ready=True,
                timeout=60,  # Longer timeout for SITL startup
                heartbeat_timeout=30  # SITL can be slower
            )

            print("✅ Connected to SITL successfully")

        except Exception as e:
            print(f"❌ Connection failed: {e}")
            print("💡 Make sure SITL is running with:")
            print("   sim_vehicle.py -v ArduCopter -f quad --console --map")
            print("   Or: sim_vehicle.py -v ArduCopter --console --map")
            raise

        # Wait for home location with timeout (SITL needs time to get GPS fix)
        print("Waiting for home location and GPS fix...")
        timeout = 30  # 30 seconds timeout
        start_time = time.time()

        while not self.vehicle.home_location:
            if time.time() - start_time > timeout:
                print("❌ Timeout waiting for home location")
                # For SITL, we can continue without home location
                break
            print(f"Waiting for GPS fix... ({time.time() - start_time:.1f}s)")
            time.sleep(2)

        if self.vehicle.home_location:
            self.home_location = self.vehicle.home_location
            print(f"✅ Home location: {self.home_location.lat:.6f}, {self.home_location.lon:.6f}")
        else:
            # Use current location as home for SITL
            current = self.vehicle.location.global_relative_frame
            print(f"Using current location as home: {current.lat:.6f}, {current.lon:.6f}")

        # Start the dead man's switch
        self.start_dead_mans_switch()

    def start_dead_mans_switch(self):
        """Start the dead man's switch monitoring thread"""
        self.dead_mans_switch_active = True
        self._running = True
        self.last_heartbeat = time.time()

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_monitor,
            daemon=True,
            name="DeadMansSwitch"
        )
        self._heartbeat_thread.start()
        print("✅ Dead man's switch activated")

    def send_heartbeat(self):
        """Call this method regularly to keep the drone active"""
        if self.dead_mans_switch_active:
            self.last_heartbeat = time.time()

    def _heartbeat_monitor(self):
        """Background thread monitoring heartbeat"""
        while self._running and self.vehicle:
            try:
                time_since_heartbeat = time.time() - self.last_heartbeat

                if time_since_heartbeat > self.heartbeat_timeout:
                    print(f"🚨 DEAD MAN'S SWITCH TRIGGERED! No heartbeat for {time_since_heartbeat:.1f}s")
                    self._trigger_emergency_action()
                    break

                time.sleep(1.0)

            except Exception as e:
                print(f"Error in dead man's switch monitor: {e}")
                self._trigger_emergency_action()
                break

    def _trigger_emergency_action(self):
        """Emergency action when dead man's switch triggers"""
        try:
            if not self.vehicle:
                return

            print("🚨 EXECUTING EMERGENCY PROTOCOL")

            # For SITL, RTL works well
            print("Setting mode to RTL (Return to Launch)")
            self.vehicle.mode = VehicleMode("RTL")

            # Alternative for SITL testing - just land where we are
            # print("Emergency landing at current location")
            # self.vehicle.mode = VehicleMode("LAND")

            self.dead_mans_switch_active = False

        except Exception as e:
            print(f"❌ Critical error in emergency action: {e}")
            try:
                if self.vehicle:
                    self.vehicle.mode = VehicleMode("LAND")
            except:
                pass

    def arm_and_takeoff(self, alt: float) -> None:
        """SITL-compatible arm and takeoff with better error handling"""
        print(f"🚁 Arming and taking off to {alt}m...")

        # Wait for vehicle to be armable (SITL needs time)
        print("Waiting for vehicle to be armable...")
        timeout = 30
        start_time = time.time()

        while not self.vehicle.is_armable:
            if time.time() - start_time > timeout:
                raise RuntimeError("Vehicle not armable after 30s")
            print(f"Vehicle not ready to arm... ({time.time() - start_time:.1f}s)")
            time.sleep(1)

        print("✅ Vehicle is armable")

        # Switch to GUIDED mode
        print("Switching to GUIDED mode...")
        self.vehicle.mode = VehicleMode("GUIDED")

        # Wait for mode change
        while self.vehicle.mode.name != "GUIDED":
            print(f"Waiting for GUIDED mode... (current: {self.vehicle.mode.name})")
            time.sleep(1)

        print("✅ In GUIDED mode")

        # Arm the vehicle
        print("Arming motors...")
        self.vehicle.armed = True

        # Wait for arming
        while not self.vehicle.armed:
            print("Waiting for arming...")
            time.sleep(1)

        print("✅ Motors armed")

        # Take off
        print(f"Taking off to {alt}m...")
        self.vehicle.simple_takeoff(alt)

        # Wait for takeoff
        while True:
            self.send_heartbeat()  # Keep sending heartbeats during takeoff

            current_alt = self.vehicle.location.global_relative_frame.alt or 0
            print(f"Altitude: {current_alt:.1f}m / {alt}m")

            if current_alt >= alt * 0.95:
                break

            # Safety check - if we're not climbing after 30 seconds, something's wrong
            if hasattr(self, '_takeoff_start'):
                if time.time() - self._takeoff_start > 30:
                    raise RuntimeError("Takeoff timeout - not gaining altitude")
            else:
                self._takeoff_start = time.time()

            time.sleep(1)

        print(f"✅ Takeoff complete at {current_alt:.1f}m")

    def goto(self, coord: Coordinate) -> None:
        """Go to coordinate with heartbeat"""
        self.send_heartbeat()
        print(f"🎯 Going to: {coord.lat:.6f}, {coord.lon:.6f}, {coord.alt}m")

        target = LocationGlobalRelative(coord.lat, coord.lon, coord.alt)
        self.vehicle.simple_goto(target)

    def set_mode(self, mode: str) -> None:
        """Set flight mode with verification"""
        self.send_heartbeat()
        print(f"Setting mode to {mode}")

        self.vehicle.mode = VehicleMode(mode)

        # Wait for mode change (important for SITL)
        timeout = 10
        start_time = time.time()
        while self.vehicle.mode.name != mode:
            if time.time() - start_time > timeout:
                print(f"⚠️  Mode change timeout. Current: {self.vehicle.mode.name}, Requested: {mode}")
                break
            time.sleep(0.5)

    def get_telemetry(self) -> Telemetry:
        """Get telemetry with heartbeat and SITL-safe attribute access"""
        self.send_heartbeat()

        if not self.vehicle:
            raise RuntimeError("Vehicle not connected")

        v = self.vehicle
        loc = v.location.global_relative_frame

        # SITL-safe battery access (might not have all attributes)
        battery_voltage = None
        battery_current = None
        battery_level = None

        try:
            if hasattr(v, 'battery') and v.battery:
                battery_voltage = getattr(v.battery, 'voltage', None)
                battery_current = getattr(v.battery, 'current', None)
                battery_level = getattr(v.battery, 'level', None)
        except:
            pass  # SITL might not simulate battery

        # Handle None values from SITL
        return Telemetry(
            lat=loc.lat or 0.0,
            lon=loc.lon or 0.0,
            alt=loc.alt or 0.0,
            heading=v.heading or 0.0,
            groundspeed=v.groundspeed or 0.0,
            armed=v.armed or False,
            mode=v.mode.name if v.mode else "UNKNOWN",
            battery_voltage=battery_voltage,
            battery_current=battery_current,
            battery_level=battery_level,
        )

    def follow_waypoints(self, path):
        """Follow waypoints with distance-based arrival detection"""
        print(f"📍 Following {len(path)} waypoints...")

        for i, wp in enumerate(path):
            self.send_heartbeat()
            print(f"Waypoint {i+1}/{len(path)}: {wp.lat:.6f}, {wp.lon:.6f}")

            self.goto(wp)

            # Wait for arrival with distance checking
            start_time = time.time()
            while time.time() - start_time < 60:  # 60 second timeout per waypoint
                self.send_heartbeat()

                current = self.vehicle.location.global_relative_frame
                distance = self._distance_to_target(current, wp)

                print(f"Distance to waypoint: {distance:.1f}m")

                if distance < 5.0:  # Within 5 meters (SITL can be less precise)
                    print(f"✅ Reached waypoint {i+1}")
                    break

                time.sleep(2)
            else:
                print(f"⚠️  Waypoint {i+1} timeout - continuing to next")

    def _distance_to_target(self, current_loc, target_coord):
        """Calculate distance using haversine formula"""
        if not current_loc.lat or not current_loc.lon:
            return float('inf')

        R = 6371000  # Earth's radius in meters

        lat1, lon1 = math.radians(current_loc.lat), math.radians(current_loc.lon)
        lat2, lon2 = math.radians(target_coord.lat), math.radians(target_coord.lon)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        return R * c

    def land(self) -> None:
        """Land with verification"""
        print("🛬 Landing...")
        self.send_heartbeat()
        self.vehicle.mode = VehicleMode("LAND")

        # Wait for landing
        while self.vehicle.armed:
            alt = self.vehicle.location.global_relative_frame.alt or 0
            print(f"Landing... altitude: {alt:.1f}m")
            time.sleep(2)
            self.send_heartbeat()

        print("✅ Landed and disarmed")

    def stop_dead_mans_switch(self):
        """Safely stop the dead man's switch"""
        print("Stopping dead man's switch...")
        self._running = False
        self.dead_mans_switch_active = False

        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)

    def close(self) -> None:
        """Clean shutdown"""
        print("Closing drone connection...")
        self.stop_dead_mans_switch()
        if self.vehicle:
            try:
                self.vehicle.close()
            except:
                pass
        print("✅ Drone connection closed")


# SITL Testing Script
async def test_sitl_connection():
    """Test script specifically for SITL"""
    print("🧪 Testing SITL connection...")

    # Common SITL connection strings
    connection_options = [
        "tcp:127.0.0.1:5762",  # Default SITL TCP
        "udp:127.0.0.1:14550", # Default SITL UDP
        "127.0.0.1:14550",     # Simple UDP
    ]

    drone = None
    for conn_str in connection_options:
        try:
            print(f"Trying connection: {conn_str}")
            drone = SITLCompatibleDrone(conn_str, heartbeat_timeout=15.0)
            drone.connect()
            break
        except Exception as e:
            print(f"Failed {conn_str}: {e}")
            continue

    if not drone or not drone.vehicle:
        print("❌ Could not connect to SITL")
        print("\n🔧 To start SITL:")
        print("cd ~/ardupilot/Tools/autotest")
        print("python sim_vehicle.py -v ArduCopter -f quad --console --map")
        return

    try:
        # Test basic operations
        print("\n📊 Vehicle status:")
        telem = drone.get_telemetry()
        print(f"Position: {telem.lat:.6f}, {telem.lon:.6f}, {telem.alt:.1f}m")
        print(f"Mode: {telem.mode}, Armed: {telem.armed}")

        # Test takeoff
        print("\n🚁 Testing takeoff...")
        drone.arm_and_takeoff(10)

        # Test waypoint
        print("\n📍 Testing waypoint navigation...")
        current_pos = drone.get_telemetry()
        # Move 50m north
        test_waypoint = Coordinate(
            lat=current_pos.lat + 0.0005,  # ~50m north
            lon=current_pos.lon,
            alt=10
        )
        drone.goto(test_waypoint)

        # Wait a bit
        import asyncio
        await asyncio.sleep(10)

        # Test dead man's switch
        print("\n💀 Testing dead man's switch (stop sending heartbeats)...")
        await asyncio.sleep(20)  # This should trigger RTL

    except KeyboardInterrupt:
        print("\n🛑 Test interrupted")
    finally:
        drone.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_sitl_connection())