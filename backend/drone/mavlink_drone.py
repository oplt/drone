import collections.abc
import math

for _name in ("MutableMapping", "MutableSequence", "MutableSet"):
    if not hasattr(collections, _name):
        setattr(collections, _name, getattr(collections.abc, _name))
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from dronekit import LocationGlobalRelative, VehicleMode, connect
from pymavlink import mavutil

from .drone_base import DroneClient, MissionAbortRequested
from .models import Coordinate, LocalCoordinate, Telemetry


@dataclass
class WaypointFollowerConfig:
    """
    Tuning parameters for the segment-based waypoint follower.

    acceptance_radius_m
        Distance to the *current* target waypoint at which the follower
        considers that waypoint reached and advances to the next one.
        Default 3.0 m suits GPS-class outdoor surveys; tighten for dense
        grid legs or loosen for fast transit legs.

    lookahead_m
        Distance to the current target at which the follower issues the
        *next* waypoint command early.  This lets the autopilot begin
        curving toward the turn before reaching the waypoint, reducing
        braking and improving survey coverage on dense grid missions.
        Must be >= acceptance_radius_m; if set to 0 lookahead is disabled.

    poll_interval_s
        How often (seconds) the position is checked inside the control
        loop.  0.2 s gives a tighter reaction than the original 1 s loop.

    max_active_leg_s
        Wall-clock limit per waypoint leg (paused time not counted).
        Raises RuntimeError when exceeded.

    on_progress
        Optional callback invoked each poll cycle:
        ``on_progress(wp_index, total_waypoints, distance_m) -> None``.
        Runs in the thread executing follow_waypoints; must not block.
    """

    acceptance_radius_m: float = 3.0
    lookahead_m: float = 5.0
    poll_interval_s: float = 0.2
    max_active_leg_s: float = 300.0
    on_progress: Callable[[int, int, float], None] | None = field(default=None, repr=False)


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
        self._mission_control_changed = threading.Event()
        self._mission_control_lock = threading.Lock()
        # Segment-follower config; replace or mutate before calling follow_waypoints
        # to tune acceptance radii, lookahead, or attach a progress callback.
        self.follower_config: WaypointFollowerConfig = WaypointFollowerConfig()

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
            local = getattr(getattr(self.vehicle, "location", None), "local_frame", None)
            if (
                local is not None
                and getattr(local, "north", None) is not None
                and getattr(local, "east", None) is not None
            ):
                logger.info("Local indoor frame is available; proceeding without GPS home")
                break
            time.sleep(1)
            tries += 1

        if self.vehicle.home_location:
            self.home_location = self.vehicle.home_location
        else:
            # Fallback: use current global frame as a provisional "home"
            loc = self.vehicle.location.global_frame
            if (
                loc is not None
                and getattr(loc, "lat", None) is not None
                and getattr(loc, "lon", None) is not None
            ):
                self.home_location = loc
            else:
                self.home_location = None

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

    def _current_takeoff_height_m(
        self,
        *,
        baseline_local_down: float | None,
        baseline_global_alt: float | None,
    ) -> tuple[float | None, str, dict[str, float]]:
        if not self.vehicle:
            return None, "unavailable", {}

        location = getattr(self.vehicle, "location", None)
        candidates: dict[str, float] = {}

        local = getattr(location, "local_frame", None)
        local_down = getattr(local, "down", None)
        if local_down is not None:
            baseline = float(baseline_local_down) if baseline_local_down is not None else 0.0
            # NED down becomes more negative as the drone climbs.
            candidates["local_ned"] = max(0.0, float(baseline) - float(local_down))

        rangefinder = getattr(self.vehicle, "rangefinder", None)
        rangefinder_distance = getattr(rangefinder, "distance", None)
        if rangefinder_distance is not None:
            candidates["rangefinder"] = max(0.0, float(rangefinder_distance))

        rel = getattr(location, "global_relative_frame", None)
        rel_alt = getattr(rel, "alt", None)
        if rel_alt is not None:
            candidates["global_relative"] = max(0.0, float(rel_alt))

        glob = getattr(location, "global_frame", None)
        glob_alt = getattr(glob, "alt", None)
        if glob_alt is not None and baseline_global_alt is not None:
            candidates["global_frame"] = max(0.0, float(glob_alt) - float(baseline_global_alt))

        if not candidates:
            return None, "unavailable", {}

        # Indoor-first source priority.
        for preferred in (
            "local_ned",
            "rangefinder",
            "global_relative",
            "global_frame",
        ):
            if preferred in candidates:
                return float(candidates[preferred]), preferred, candidates

        return None, "unavailable", candidates

    def arm_and_takeoff(self, alt: float) -> None:
        if not self.vehicle:
            raise RuntimeError("Vehicle not connected")

        target_alt_m = float(alt)
        baseline_local_down = getattr(
            getattr(getattr(self.vehicle, "location", None), "local_frame", None),
            "down",
            None,
        )
        baseline_global_alt = getattr(
            getattr(getattr(self.vehicle, "location", None), "global_frame", None),
            "alt",
            None,
        )

        while not self.vehicle.is_armable:
            time.sleep(1)

        self.vehicle.mode = VehicleMode("GUIDED")
        self.vehicle.armed = True

        while not self.vehicle.armed:
            time.sleep(1)

        self.vehicle.simple_takeoff(target_alt_m)

        source_name = "unavailable"
        started_at = time.monotonic()
        timeout_s = max(45.0, target_alt_m * 15.0)
        last_candidates: dict[str, float] = {}
        next_progress_log_at = started_at + 5.0

        # More tolerant for indoor missions:
        # for 4.0m this becomes 3.68m, which would have passed your logged case.
        required_alt_m = max(target_alt_m * 0.92, target_alt_m - 0.35)

        # Require a few consecutive confirmations to avoid one-sample spikes.
        stable_hits = 0
        stable_hits_required = 3

        while True:
            if self._mission_abort_requested.is_set():
                raise MissionAbortRequested("Operator abort requested during takeoff")

            current_alt, source_name, last_candidates = self._current_takeoff_height_m(
                baseline_local_down=baseline_local_down,
                baseline_global_alt=baseline_global_alt,
            )

            if current_alt is not None and current_alt >= required_alt_m:
                stable_hits += 1
                if stable_hits >= stable_hits_required:
                    logger.info(
                        "Takeoff reached %.2fm using %s altitude feedback "
                        "(target=%.2fm, required=%.2fm)",
                        current_alt,
                        source_name,
                        target_alt_m,
                        required_alt_m,
                    )
                    break
            else:
                stable_hits = 0

            now = time.monotonic()
            if now >= next_progress_log_at:
                logger.info(
                    "Takeoff progress %.2fm / %.2fm via %s | required=%.2fm | candidates=%s",
                    float(current_alt or 0.0),
                    target_alt_m,
                    source_name,
                    required_alt_m,
                    {key: round(value, 2) for key, value in last_candidates.items()},
                )
                next_progress_log_at = now + 5.0

            if now - started_at > timeout_s:
                mode_name = getattr(getattr(self.vehicle, "mode", None), "name", None) or "UNKNOWN"
                raise TimeoutError(
                    "Timed out waiting for takeoff completion "
                    f"(target={target_alt_m:.2f}m, required={required_alt_m:.2f}m, "
                    f"source={source_name}, best={float(current_alt or 0.0):.2f}m, "
                    f"mode={mode_name}, "
                    f"candidates={{{', '.join(f'{key}: {value:.2f}' for key, value in last_candidates.items())}}})"
                )

            self._mission_control_changed.wait(timeout=0.2)
            self._mission_control_changed.clear()

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
            self._mission_control_changed.set()
            # Prefer LOITER; BRAKE as fallback where supported.
            return self._set_mode_best_effort("LOITER", "BRAKE")

    def resume_mission(self) -> bool:
        if not self.vehicle:
            return False
        with self._mission_control_lock:
            self._mission_pause_requested.clear()
            self._mission_control_changed.set()
            # Guided mode allows simple_goto waypoint execution to continue.
            return self._set_mode_best_effort("GUIDED", "AUTO")

    def abort_mission(self) -> bool:
        if not self.vehicle:
            return False
        with self._mission_control_lock:
            self._mission_abort_requested.set()
            self._mission_pause_requested.clear()
            self._mission_control_changed.set()
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
        glob = getattr(loc, "global_frame", None)
        local = getattr(loc, "local_frame", None)
        bat = getattr(v, "battery", None)
        gps = getattr(v, "gps_0", None)
        home = getattr(v, "home_location", None) or self.home_location
        local_north = getattr(local, "north", None)
        local_east = getattr(local, "east", None)
        local_down = getattr(local, "down", None)
        local_position_ok = (
            local_north is not None and local_east is not None and local_down is not None
        )
        rangefinder = getattr(v, "rangefinder", None)
        obstacle_distance = getattr(rangefinder, "distance", None)
        lat = getattr(rel, "lat", None) if rel is not None else None
        lon = getattr(rel, "lon", None) if rel is not None else None
        alt = getattr(rel, "alt", None) if rel is not None else None
        if lat is None:
            lat = getattr(glob, "lat", None)
        if lon is None:
            lon = getattr(glob, "lon", None)
        if alt is None:
            alt = getattr(glob, "alt", None)
        if alt is None and local_down is not None:
            alt = -float(local_down)
        home_lat = getattr(home, "lat", None) if home is not None else None
        home_lon = getattr(home, "lon", None) if home is not None else None
        if lat is None:
            lat = home_lat if home_lat is not None else 0.0
        if lon is None:
            lon = home_lon if home_lon is not None else 0.0
        if alt is None:
            alt = 0.0
        if home_lat is None or home_lon is None:
            home_set = None if local_position_ok else False
        else:
            home_set = True
        heading = getattr(v, "heading", None)
        groundspeed = getattr(v, "groundspeed", None)
        mode_name = getattr(getattr(v, "mode", None), "name", None) or "UNKNOWN"
        return Telemetry(
            lat=float(lat),
            lon=float(lon),
            alt=float(alt),
            heading=float(heading) if heading is not None else 0.0,
            groundspeed=float(groundspeed) if groundspeed is not None else 0.0,
            mode=str(mode_name),
            battery_voltage=getattr(bat, "voltage", None),
            battery_current=getattr(bat, "current", None),
            battery_remaining=getattr(bat, "level", None),
            gps_fix_type=getattr(gps, "fix_type", None),
            hdop=getattr(gps, "eph", None),
            satellites_visible=getattr(gps, "satellites_visible", None),
            heartbeat_age_s=getattr(v, "last_heartbeat", None),
            is_armable=getattr(v, "is_armable", None),
            home_set=home_set,
            home_lat=home_lat,
            home_lon=home_lon,
            ekf_ok=getattr(v, "ekf_ok", None),
            local_north_m=float(local_north) if local_north is not None else None,
            local_east_m=float(local_east) if local_east is not None else None,
            local_down_m=float(local_down) if local_down is not None else None,
            local_position_ok=local_position_ok,
            local_origin_ok=local_position_ok or home_set is True,
            odometry_healthy=local_position_ok,
            odometry_drift_m=None,
            lidar_healthy=(
                bool(obstacle_distance > 0.0) if obstacle_distance is not None else None
            ),
            obstacle_distance_m=(
                float(obstacle_distance) if obstacle_distance is not None else None
            ),
            ceiling_distance_m=None,
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
                p1=0.0,  # camera id
                p2=interval,  # capture interval (s)
                p3=0.0,  # 0 => keep capturing until explicit stop
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

    def follow_waypoints(self, path) -> None:
        """
        Fly the drone through every Coordinate in *path* using the
        segment-based follower.  Tune behaviour by setting
        ``self.follower_config`` before calling.
        """
        self._mission_abort_requested.clear()
        self._mission_pause_requested.clear()
        self._fly_segment_path(list(path), self.follower_config)

    def _fly_segment_path(
        self,
        path: list[Coordinate],
        config: WaypointFollowerConfig,
    ) -> None:
        """
        Segment-based inner loop for follow_waypoints.

        For each waypoint i:
          1. Issue goto(path[i]).
          2. Poll every config.poll_interval_s.
          3. When distance < config.lookahead_m and the next waypoint exists,
             issue goto(path[i+1]) once (turn anticipation — vehicle begins
             curving before reaching the acceptance sphere).
          4. When distance < config.acceptance_radius_m advance to i+1.
          5. Track paused time so the per-leg timeout counts only active
             flight time.
          6. Raise MissionAbortRequested on operator abort.
          7. Raise RuntimeError when a leg exceeds config.max_active_leg_s.
        """
        n = len(path)
        if n == 0:
            return

        cfg = config
        lookahead_m = max(0.0, cfg.lookahead_m)

        for i, target in enumerate(path):
            self.goto(target)
            logger.debug("Segment follower: heading to wp %d/%d %s", i + 1, n, target)

            start_time = time.monotonic()
            paused_started_at: float | None = None
            paused_total_s = 0.0
            was_paused = False
            lookahead_issued = False  # guard: only issue next-wp command once per leg

            while True:
                if self._mission_abort_requested.is_set():
                    raise MissionAbortRequested("Operator abort requested")

                if self._mission_pause_requested.is_set():
                    if paused_started_at is None:
                        paused_started_at = time.monotonic()
                        was_paused = True
                    self._mission_control_changed.wait(timeout=cfg.poll_interval_s)
                    self._mission_control_changed.clear()
                    continue

                # Accumulate paused time after unpausing.
                if paused_started_at is not None:
                    paused_total_s += time.monotonic() - paused_started_at
                    paused_started_at = None
                if was_paused:
                    # Re-issue current target so autopilot resumes toward it.
                    self.goto(target)
                    lookahead_issued = False  # reset — drone may have drifted
                    was_paused = False

                current = self.vehicle.location.global_relative_frame
                dist = self._distance_to_target(current, target)

                if cfg.on_progress is not None:
                    try:
                        cfg.on_progress(i, n, dist)
                    except Exception:
                        logger.exception("WaypointFollowerConfig.on_progress raised")

                # Lookahead: begin commanding the next waypoint early so the
                # autopilot can start curving into the turn before reaching
                # the acceptance sphere.
                if not lookahead_issued and lookahead_m > 0 and dist < lookahead_m and i + 1 < n:
                    self.goto(path[i + 1])
                    lookahead_issued = True
                    logger.debug(
                        "Segment follower: lookahead fired at %.1f m — pre-commanding wp %d/%d",
                        dist,
                        i + 2,
                        n,
                    )

                if dist < cfg.acceptance_radius_m:
                    logger.debug("Segment follower: wp %d/%d accepted at %.1f m", i + 1, n, dist)
                    break

                active_elapsed_s = (time.monotonic() - start_time) - paused_total_s
                if active_elapsed_s > cfg.max_active_leg_s:
                    raise RuntimeError(
                        f"Waypoint leg {i + 1}/{n} timed out after "
                        f"{cfg.max_active_leg_s:.0f}s active flight time "
                        f"(dist={dist:.1f}m)"
                    )

                self._mission_control_changed.wait(timeout=cfg.poll_interval_s)
                self._mission_control_changed.clear()

    def _send_local_position_target(self, coord: LocalCoordinate) -> None:
        if not self.vehicle:
            raise RuntimeError("Vehicle not connected")

        master = getattr(self.vehicle, "_master", None)
        target_system = int(getattr(master, "target_system", 1) or 1)
        target_component = int(getattr(master, "target_component", 1) or 1)
        type_mask = (
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_VX_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VY_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VZ_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AX_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AY_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AZ_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE
        )
        yaw_rad = 0.0
        if coord.yaw_deg is None:
            type_mask |= mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_IGNORE
        else:
            yaw_rad = math.radians(float(coord.yaw_deg))

        msg = self.vehicle.message_factory.set_position_target_local_ned_encode(
            0,
            target_system,
            target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            int(type_mask),
            float(coord.north_m),
            float(coord.east_m),
            float(coord.down_m),
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            float(yaw_rad),
            0.0,
        )
        self.vehicle.send_mavlink(msg)
        self.vehicle.flush()

    def _local_distance_to_target(self, coord: LocalCoordinate) -> float:
        if not self.vehicle:
            raise RuntimeError("Vehicle not connected")
        local = getattr(getattr(self.vehicle, "location", None), "local_frame", None)
        if local is None:
            raise RuntimeError("Vehicle local frame is not available")
        north = getattr(local, "north", None)
        east = getattr(local, "east", None)
        down = getattr(local, "down", None)
        if north is None or east is None or down is None:
            raise RuntimeError("Vehicle local position is incomplete")
        return math.sqrt(
            (float(north) - float(coord.north_m)) ** 2
            + (float(east) - float(coord.east_m)) ** 2
            + (float(down) - float(coord.down_m)) ** 2
        )

    def follow_local_setpoints(self, path):
        self._mission_abort_requested.clear()
        self._mission_pause_requested.clear()
        for coord in path:
            self._send_local_position_target(coord)

            start_time = time.monotonic()
            paused_started_at = None
            paused_total_s = 0.0
            was_paused = False
            max_active_leg_s = 180.0
            while True:
                if self._mission_abort_requested.is_set():
                    raise MissionAbortRequested("Operator abort requested")

                if self._mission_pause_requested.is_set():
                    if paused_started_at is None:
                        paused_started_at = time.monotonic()
                        was_paused = True
                    self._mission_control_changed.wait(timeout=0.2)
                    self._mission_control_changed.clear()
                    continue

                if paused_started_at is not None:
                    paused_total_s += time.monotonic() - paused_started_at
                    paused_started_at = None
                if was_paused:
                    self._send_local_position_target(coord)
                    was_paused = False

                distance = self._local_distance_to_target(coord)
                if distance < 0.8:
                    break

                active_elapsed_s = (time.monotonic() - start_time) - paused_total_s
                if active_elapsed_s > max_active_leg_s:
                    raise RuntimeError(
                        f"Local setpoint leg timeout after {max_active_leg_s:.0f}s active flight time"
                    )

                self._mission_control_changed.wait(timeout=0.2)
                self._mission_control_changed.clear()

    def _distance_to_target(self, current_loc, target_coord):
        """Calculate distance to target coordinate"""
        from math import atan2, cos, radians, sin, sqrt

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
