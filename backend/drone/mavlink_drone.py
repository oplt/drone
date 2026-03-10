import collections.abc

for _name in ("MutableMapping", "MutableSequence", "MutableSet"):
    if not hasattr(collections, _name):
        setattr(collections, _name, getattr(collections.abc, _name))
import time
import threading
from .models import Coordinate, Telemetry
from .drone_base import DroneClient, MissionAbortRequested
import logging
from dronekit import connect, VehicleMode, LocationGlobalRelative
from pymavlink import mavutil


logger = logging.getLogger(__name__)


class MavlinkDrone(DroneClient):
    def __init__(self, connection_str: str, heartbeat_timeout: float):
        self.connection_str = connection_str
        self.vehicle = None
        self.heartbeat_timeout = heartbeat_timeout
        self.last_heartbeat = time.time()
        self.dead_mans_switch_active = False
        self.dead_mans_switch_triggered = False
        self.home_location = None
        self._heartbeat_thread = None
        self._running = False
        self._groundspeed_override_mps = None
        self._capture_mode = None
        self._mission_pause_requested = threading.Event()
        self._mission_abort_requested = threading.Event()
        self._mission_control_lock = threading.Lock()

    def connect(self) -> None:
        self.vehicle = connect(
            self.connection_str,
            wait_ready=True,
            heartbeat_timeout=self.heartbeat_timeout,
        )

        # Wait until autopilot sets home_location (requires GPS fix; often set after arm, but we try early)
        # print("Waiting for home location...")
        logger.info("Waiting for home location...")
        tries = 0
        while not getattr(self.vehicle, "home_location", None) and tries < 30:
            time.sleep(1)
            tries += 1

        if self.vehicle.home_location:
            self.home_location = self.vehicle.home_location
        else:
            # Fallback: use current global frame as a provisional "home"
            loc = self.vehicle.location.global_frame
            self.home_location = loc

        # print(f"Home location set: {self.home_location}")
        logger.info(f"Home location set: {self.home_location}")

        """this function and heart beat flow should be added on raspberry pi on drone"""
        # Start the dead man's switch monitoring
        # self.start_dead_mans_switch()


    def get_home_amsl(self) -> float:
        # AMSL in meters (DroneKit global_frame.alt)
        alt = getattr(self.vehicle.location.global_frame, "alt", None)
        if alt is None:
            raise RuntimeError("global_frame.alt not available (AMSL).")
        return float(alt)

    """SHOULD BE MODIFIED AND ADDED TO RASPBERRY PI ON DRONE"""

    def start_dead_mans_switch(self):
        """Start the dead man's switch monitoring thread"""
        self.dead_mans_switch_active = True
        self.dead_mans_switch_triggered = False
        self._running = True
        self.last_heartbeat = time.time()  # Reset heartbeat

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_monitor, daemon=True, name="DeadMansSwitch"
        )
        self._heartbeat_thread.start()
        logger.info("Dead man's switch activated")
        # print("Dead man's switch activated")

    # def send_heartbeat(self):
    #     """Call this method regularly from your main application to keep the drone active"""
    #     if self.dead_mans_switch_active:
    #         self.last_heartbeat = time.time()
    #         logger.info(f"Heartbeat sent at {self.last_heartbeat}")
    #         # print(f"Heartbeat sent at {self.last_heartbeat}")  # Uncomment for debugging

    """SHOULD BE MODIFIED AND ADDED TO RASPBERRY PI ON DRONE"""

    def _heartbeat_monitor(self):
        """Background thread that monitors heartbeat and triggers emergency actions"""
        while self._running and self.vehicle:
            try:
                time_since_heartbeat = time.time() - self.last_heartbeat

                if time_since_heartbeat > self.heartbeat_timeout:
                    # print(f"⚠️  DEAD MAN'S SWITCH TRIGGERED! No heartbeat for {time_since_heartbeat:.1f}s")
                    logger.info(
                        f"⚠️  DEAD MAN'S SWITCH TRIGGERED! No heartbeat for {time_since_heartbeat:.1f}s"
                    )
                    self._trigger_emergency_action()
                    break  # Exit the monitoring loop after triggering

                time.sleep(1.0)  # Check every second

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
            # self.send_heartbeat()

            current_alt = self.vehicle.location.global_relative_frame.alt
            if current_alt >= alt * 0.95:
                break
            time.sleep(1)

    def goto(self, coord: Coordinate) -> None:
        # Send heartbeat before major operations
        # self.send_heartbeat()

        target = LocationGlobalRelative(coord.lat, coord.lon, coord.alt)
        groundspeed = self._groundspeed_override_mps
        if groundspeed and groundspeed > 0:
            self.vehicle.simple_goto(target, groundspeed=float(groundspeed))
        else:
            self.vehicle.simple_goto(target)

    def set_mode(self, mode: str) -> None:
        # self.send_heartbeat()
        self.vehicle.mode = VehicleMode(mode)

    def _set_mode_best_effort(self, *modes: str) -> bool:
        if not self.vehicle:
            return False
        for mode in modes:
            try:
                self.vehicle.mode = VehicleMode(mode)
                logger.info("Mission control switched mode to %s", mode)
                return True
            except Exception as exc:
                logger.warning("Failed to set mode '%s': %s", mode, exc)
        return False

    def pause_mission(self) -> bool:
        if not self.vehicle:
            return False
        with self._mission_control_lock:
            self._mission_pause_requested.set()
            # Prefer LOITER; BRAKE as fallback where supported.
            return self._set_mode_best_effort("LOITER", "BRAKE")

    def resume_mission(self) -> bool:
        if not self.vehicle:
            return False
        with self._mission_control_lock:
            self._mission_pause_requested.clear()
            # Guided mode allows simple_goto waypoint execution to continue.
            return self._set_mode_best_effort("GUIDED", "AUTO")

    def abort_mission(self) -> bool:
        if not self.vehicle:
            return False
        with self._mission_control_lock:
            self._mission_abort_requested.set()
            self._mission_pause_requested.clear()
            # RTL first for safe recovery, LAND fallback.
            return self._set_mode_best_effort("RTL", "LAND")

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
        gps = getattr(v, "gps_0", None)
        home = getattr(v, "home_location", None) or self.home_location
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
            gps_fix_type=getattr(gps, "fix_type", None),
            hdop=getattr(gps, "eph", None),
            satellites_visible=getattr(gps, "satellites_visible", None),
            heartbeat_age_s=getattr(v, "last_heartbeat", None),
            is_armable=getattr(v, "is_armable", None),
            home_set=home is not None,
            home_lat=getattr(home, "lat", None) if home is not None else None,
            home_lon=getattr(home, "lon", None) if home is not None else None,
            ekf_ok=getattr(v, "ekf_ok", None),
        )

    def set_groundspeed(self, speed_mps: float) -> bool:
        if not self.vehicle:
            return False
        speed = float(speed_mps)
        if speed <= 0:
            raise ValueError("Groundspeed must be > 0")
        self.vehicle.groundspeed = speed
        self._groundspeed_override_mps = speed
        return True

    def _send_command_long(
        self,
        *,
        command: int,
        p1: float = 0.0,
        p2: float = 0.0,
        p3: float = 0.0,
        p4: float = 0.0,
        p5: float = 0.0,
        p6: float = 0.0,
        p7: float = 0.0,
    ) -> None:
        if not self.vehicle:
            raise RuntimeError("Vehicle not connected")
        master = getattr(self.vehicle, "_master", None)
        target_system = int(getattr(master, "target_system", 1) or 1)
        target_component = int(getattr(master, "target_component", 1) or 1)
        msg = self.vehicle.message_factory.command_long_encode(
            target_system,
            target_component,
            int(command),
            0,  # confirmation
            float(p1),
            float(p2),
            float(p3),
            float(p4),
            float(p5),
            float(p6),
            float(p7),
        )
        self.vehicle.send_mavlink(msg)
        self.vehicle.flush()

    def start_image_capture(
        self,
        *,
        mode: str = "distance",
        distance_m: float | None = None,
        interval_s: float | None = None,
    ) -> bool:
        if not self.vehicle:
            return False
        normalized_mode = str(mode or "distance").strip().lower()
        if normalized_mode == "distance":
            dist = float(distance_m or 0.0)
            if dist <= 0:
                raise ValueError("distance_m must be > 0 for distance capture mode")
            self._send_command_long(
                command=mavutil.mavlink.MAV_CMD_DO_SET_CAM_TRIGG_DIST,
                p1=dist,
                p2=0.0,
                p3=0.0,
            )
            self._capture_mode = "distance"
            return True

        if normalized_mode == "time":
            interval = float(interval_s or 0.0)
            if interval <= 0:
                raise ValueError("interval_s must be > 0 for time capture mode")
            self._send_command_long(
                command=mavutil.mavlink.MAV_CMD_IMAGE_START_CAPTURE,
                p1=0.0,       # camera id
                p2=interval,  # capture interval (s)
                p3=0.0,       # 0 => keep capturing until explicit stop
                p4=0.0,
            )
            self._capture_mode = "time"
            return True

        raise ValueError(f"Unsupported image capture mode: {mode!r}")

    def stop_image_capture(self) -> bool:
        if not self.vehicle:
            return False
        sent = False
        try:
            self._send_command_long(
                command=mavutil.mavlink.MAV_CMD_IMAGE_STOP_CAPTURE,
                p1=0.0,
            )
            sent = True
        except Exception as exc:
            logger.warning("Failed to send MAV_CMD_IMAGE_STOP_CAPTURE: %s", exc)

        try:
            self._send_command_long(
                command=mavutil.mavlink.MAV_CMD_DO_SET_CAM_TRIGG_DIST,
                p1=0.0,
            )
            sent = True
        except Exception as exc:
            logger.warning("Failed to disable MAV_CMD_DO_SET_CAM_TRIGG_DIST: %s", exc)

        self._capture_mode = None
        return sent

    def start_video_recording(self) -> bool:
        if not self.vehicle:
            return False

        command = getattr(mavutil.mavlink, "MAV_CMD_VIDEO_START_CAPTURE", None)
        if command is None:
            logger.warning("MAV_CMD_VIDEO_START_CAPTURE is unavailable in this pymavlink build")
            return False

        try:
            self._send_command_long(
                command=command,
                p1=0.0,  # camera id: all/default camera
                p2=1.0,  # status frequency in Hz
                p3=0.0,
                p4=0.0,
            )
            return True
        except Exception as exc:
            logger.warning("Failed to send MAV_CMD_VIDEO_START_CAPTURE: %s", exc)
            return False

    def stop_video_recording(self) -> bool:
        if not self.vehicle:
            return False

        command = getattr(mavutil.mavlink, "MAV_CMD_VIDEO_STOP_CAPTURE", None)
        if command is None:
            logger.warning("MAV_CMD_VIDEO_STOP_CAPTURE is unavailable in this pymavlink build")
            return False

        try:
            self._send_command_long(
                command=command,
                p1=0.0,  # camera id: all/default camera
            )
            return True
        except Exception as exc:
            logger.warning("Failed to send MAV_CMD_VIDEO_STOP_CAPTURE: %s", exc)
            return False

    def download_captured_images(self, *, destination_dir: str) -> list[str]:
        # DroneKit+MAVLink path in this adapter does not expose camera file transfer.
        # A companion sync process should populate destination_dir instead.
        logger.info(
            "Direct camera image download is unsupported by MavlinkDrone adapter; "
            "destination_dir=%s",
            destination_dir,
        )
        return []

    def follow_waypoints(self, path):
        self._mission_abort_requested.clear()
        self._mission_pause_requested.clear()
        for wp in path:
            # self.send_heartbeat()  # Heartbeat before each waypoint
            self.goto(wp)

            # Wait for waypoint with mission-control awareness.
            start_time = time.monotonic()
            paused_started_at = None
            paused_total_s = 0.0
            was_paused = False
            max_active_leg_s = 300.0
            while True:
                if self._mission_abort_requested.is_set():
                    raise MissionAbortRequested("Operator abort requested")

                if self._mission_pause_requested.is_set():
                    if paused_started_at is None:
                        paused_started_at = time.monotonic()
                        was_paused = True
                    time.sleep(0.4)
                    continue

                if paused_started_at is not None:
                    paused_total_s += time.monotonic() - paused_started_at
                    paused_started_at = None
                if was_paused:
                    # Re-send target after unpausing to continue route reliably.
                    self.goto(wp)
                    was_paused = False

                # Check if we're close enough to the waypoint
                current = self.vehicle.location.global_relative_frame
                distance = self._distance_to_target(current, wp)

                if distance < 2.0:  # Within 2 meters
                    break

                active_elapsed_s = (time.monotonic() - start_time) - paused_total_s
                if active_elapsed_s > max_active_leg_s:
                    raise RuntimeError(
                        f"Waypoint leg timeout after {max_active_leg_s:.0f}s active flight time"
                    )

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

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return R * c

    def land(self) -> None:
        # self.send_heartbeat()
        self.vehicle.mode = VehicleMode("LAND")

    def wait_until_disarmed(self, timeout_s: float = 900):
        """Block until vehicle.armed == False or raise TimeoutError."""
        start = time.time()
        while (time.time() - start) < timeout_s:
            if self.vehicle is None:
                raise RuntimeError("Vehicle unavailable while waiting for disarm")

            if not getattr(self.vehicle, "armed", False):
                return

            # self.send_heartbeat()  # keeps dead-man switch happy
            time.sleep(1.0)

        if self.vehicle is not None and getattr(self.vehicle, "armed", False):
            mode = getattr(getattr(self.vehicle, "mode", None), "name", None)
            raise TimeoutError(
                f"Timed out after {timeout_s}s waiting for disarm (mode={mode or 'unknown'})"
            )

    def stop_dead_mans_switch(self):
        """Safely disable the dead man's switch"""
        # print("Stopping dead man's switch...")
        logger.info("Stopping dead man's switch...")
        self._running = False
        self.dead_mans_switch_active = False

        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)

    def close(self) -> None:
        self.stop_dead_mans_switch()
        if self.vehicle:
            self.vehicle.close()
