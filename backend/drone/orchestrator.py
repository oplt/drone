import asyncio
import time
import logging
from .models import Coordinate
from .drone_base import DroneClient
from backend.map.google_maps import GoogleMapsClient
from backend.video.stream import DroneVideoStream
from backend.analysis.llm import LLMAnalyzer
from backend.messaging.mqtt import MqttClient
from backend.messaging.opcua import DroneOpcUaServer
from backend.db.repository import TelemetryRepository
from backend.config import settings
from backend.analysis.range_estimator import SimpleWhPerKmModel, RangeEstimateResult
from backend.utils.geo import haversine_km, _coord_from_home
from backend.utils.telemetry_publisher_sim import ArduPilotTelemetryPublisher

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(
        self,
        drone: DroneClient,
        maps: GoogleMapsClient,
        analyzer: LLMAnalyzer,
        mqtt: MqttClient,
        opcua: DroneOpcUaServer,
        video: DroneVideoStream,
        telemetry_repo: TelemetryRepository,
        publisher: ArduPilotTelemetryPublisher,
    ):
        self.drone = drone
        self.maps = maps
        self.analyzer = analyzer
        self.mqtt = mqtt
        self.opcua = opcua
        self.video = video
        self.repo = telemetry_repo
        self.range_model = SimpleWhPerKmModel()
        self._running = True
        self._dest_coord: Coordinate | None = None
        # self._heartbeat_task = None
        self.publisher = publisher
        self._telemetry_interval = settings.telem_log_interval_sec
        self._flight_id = None
        self._ingest_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=2000)
        self._raw_event_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=2000)
        self._video_health_interval = 5.0  # Check video health every 5 seconds

    @property
    def flight_id(self):
        return self._flight_id

    async def heartbeat_task(self):
        logger.info("Starting heartbeat task...")
        try:
            while self._running:
                self.mqtt.publish(
                    "drone/heartbeat",
                    {"timestamp": time.time(), "status": "alive"},
                    qos=1,
                )
                await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.warning(f"Heartbeat task error: {e}")

    async def telemetry_publish_task(self):
        """Manage the telemetry publisher lifecycle"""
        try:
            # Start publisher in a thread (non-blocking)
            if not await asyncio.to_thread(self.publisher.start):
                logger.error("Failed to start telemetry publisher")
                return

            # Just keep this task alive while publisher runs
            while self._running and self.publisher.is_alive():
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Telemetry publisher error: {e}")
        finally:
            if self.publisher.is_running:
                await asyncio.to_thread(self.publisher.stop)

    async def video_health_monitor_task(self):
        """Monitor video stream health and publish status"""
        logger.info("Starting video health monitor task...")

        while self._running:
            try:
                if self.video:
                    # Get video connection status
                    status = self.video.get_connection_status()

                    # Publish video health status to MQTT
                    self.mqtt.publish(
                        "drone/video/status",
                        {
                            "timestamp": time.time(),
                            "healthy": status["healthy"],
                            "frame_count": status["frame_count"],
                            "fps": status["fps"],
                            "resolution": status["resolution"],
                            "recording": status["recording"],
                            "recording_file": status["recording_file"],
                        },
                        qos=1,
                    )

                    # Update OPC UA with video status
                    await self.opcua.update_video_status(
                        healthy=status["healthy"],
                        fps=status["fps"],
                        recording=status["recording"],
                    )

                    # Log warnings if video is unhealthy
                    if not status["healthy"]:
                        logging.warning("Video stream is unhealthy")
                        self.mqtt.publish(
                            "drone/warnings",
                            {
                                "type": "video_stream_unhealthy",
                                "message": "Video stream connection issues detected",
                                "timestamp": time.time(),
                            },
                            qos=1,
                        )

                await asyncio.sleep(self._video_health_interval)

            except Exception as e:
                logger.error(f"Error in video health monitor: {e}")
                await asyncio.sleep(1.0)

    async def _raw_event_ingest_worker(self):
        BATCH_SIZE = 1000
        INTERVAL_S = 0.25
        buffer = []
        logger.info("Starting _raw_event_ingest_worker")

        try:
            while self._running:
                try:
                    item = await asyncio.wait_for(
                        self._raw_event_queue.get(), timeout=INTERVAL_S
                    )
                    buffer.append(item)

                    # drain quickly
                    while len(buffer) < BATCH_SIZE:
                        try:
                            buffer.append(self._raw_event_queue.get_nowait())
                        except asyncio.QueueEmpty:
                            break

                    if self._flight_id is None:
                        buffer.clear()
                        continue

                    if buffer:
                        await self.repo.add_mavlink_events_many(self._flight_id, buffer)
                        # Only call task_done if you rely on queue.join()
                        for _ in range(len(buffer)):
                            self._raw_event_queue.task_done()
                        buffer.clear()

                except asyncio.TimeoutError:
                    if buffer and self._flight_id is not None:
                        await self.repo.add_mavlink_events_many(self._flight_id, buffer)
                        for _ in range(len(buffer)):
                            self._raw_event_queue.task_done()
                        buffer.clear()

        except asyncio.CancelledError:
            # graceful exit: best effort flush
            if buffer and self._flight_id is not None:
                try:
                    await self.repo.add_mavlink_events_many(self._flight_id, buffer)
                except Exception:
                    pass
            raise

    # backend/drone/orchestrator.py

    async def mqtt_subscriber_task(self):
        try:
            while self._flight_id is None:
                logger.info(
                    "Waiting for flight_id to be set before starting MQTT subscriber..."
                )
                await asyncio.sleep(0.5)

            logger.info(f"Starting MQTT subscriber with flight_id: {self._flight_id}")

            self.mqtt.attach_raw_event_queue(self._raw_event_queue)

            try:
                ok = await asyncio.to_thread(
                    self.mqtt.subscribe_to_topics, self._flight_id
                )
            except Exception as e:
                logger.exception("MQTT subscribe_to_topics crashed", exc_info=e)
                return

            if not ok:
                logger.error(
                    "MQTT subscribe_to_topics returned False (no exception). "
                    "Likely connection/auth/topic-subscribe failure. "
                    "Check broker/port/credentials and have subscribe_to_topics log a reason."
                )
                return

            logger.info("MQTT subscriber started and listening for messages")
            while self._running:
                await asyncio.sleep(1)

        except Exception as e:
            logger.exception(f"Mqtt broker subscribe error: {e}")

    async def emergency_monitor_task(self):
        """Monitor for emergency conditions and handle them"""
        while self._running:
            try:
                # Check if dead man's switch was triggered
                if hasattr(self.drone, "dead_mans_switch_active"):
                    if not self.drone.dead_mans_switch_active and self.drone.vehicle:
                        # Dead man's switch was triggered!
                        self.mqtt.publish(
                            "drone/emergency",
                            {
                                "type": "dead_mans_switch_triggered",
                                "message": "Connection lost - drone executing emergency protocol",
                                "timestamp": time.time(),
                            },
                            qos=2,
                        )  # QoS 2 for critical emergency messages

                        # Stop all other operations
                        self._running = False
                        break
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.info(f"Error in emergency monitor: {e}")
                # print(f"Error in emergency monitor: {e}")
                await asyncio.sleep(1.0)

    async def _preflight_range_check(
        self, home: Coordinate, start: Coordinate, dest: Coordinate
    ) -> RangeEstimateResult:
        """Range check for a simple home→start→dest→home route."""
        # Create a simple route for checking
        route = [start, dest]
        return await self._preflight_range_check_route(home, route)

    async def fly_route(self, start, dest, cruise_alt=30.0):
        # start = await asyncio.to_thread(self.maps.geocode, start_addr); start.alt = cruise_alt
        # dest  = await asyncio.to_thread(self.maps.geocode, end_addr); dest.alt = cruise_alt
        self._running = True

        # Create flight record if not already created
        if self._flight_id is None:
            self._flight_id = await self.repo.create_flight(
                start_lat=start.lat,
                start_lon=start.lon,
                start_alt=start.alt,
                dest_lat=dest.lat,
                dest_lon=dest.lon,
                dest_alt=dest.alt,
            )
            logger.info(f"Created flight with ID: {self._flight_id}")

        await self.repo.add_event(
            self._flight_id, "mission_created", {"alt": cruise_alt}
        )

        self._dest_coord = dest

        await asyncio.sleep(1.0)

        await self.repo.add_event(self._flight_id, "connected", {})

        # Preflight range check (can hard-fail if you want)
        home = _coord_from_home(self.drone.home_location)

        preflight = await self._preflight_range_check(home, start, dest)
        if not preflight.feasible and settings.enforce_preflight_range:
            raise RuntimeError(preflight.reason)
        await asyncio.to_thread(self.drone.arm_and_takeoff, cruise_alt)
        await self.repo.add_event(self._flight_id, "takeoff", {})

        path = list(self.maps.waypoints_between(start, dest, steps=6))
        await asyncio.to_thread(self.drone.follow_waypoints, path)
        await self.repo.add_event(self._flight_id, "reached_destination", {})

        # Return to takeoff home using RTL and wait for landing
        self.drone.set_mode("RTL")
        await self.repo.add_event(self._flight_id, "rtl_initiated", {})
        await asyncio.to_thread(self.drone.wait_until_disarmed, 900)
        await self.repo.add_event(self._flight_id, "landed_home", {})
        await self.repo.finish_flight(
            self._flight_id, status="completed", note="RTL to home completed"
        )

    def _total_route_distance_km(
        self, home: Coordinate, route: list[Coordinate]
    ) -> float:
        """Total mission distance (km): home→route[0]→...→route[-1]→home."""
        if not route:
            return 0.0
        total = haversine_km(home.lat, home.lon, route[0].lat, route[0].lon)
        for a, b in zip(route, route[1:]):
            total += haversine_km(a.lat, a.lon, b.lat, b.lon)
        total += haversine_km(route[-1].lat, route[-1].lon, home.lat, home.lon)
        return total

    async def _preflight_range_check_route(
        self, home: Coordinate, route: list[Coordinate]
    ) -> RangeEstimateResult:
        """Range check over the full clicked route."""
        from backend.config import settings

        distance_km = self._total_route_distance_km(home, route)

        t = self.drone.get_telemetry()
        level_frac = (
            None
            if t.battery_remaining is None
            else max(0.0, min(1.0, float(t.battery_remaining) / 100.0))
        )

        v_kmh = max(0.1, settings.cruise_speed_mps * 3.6)
        wh_per_km = settings.cruise_power_w / v_kmh
        required_Wh = distance_km * wh_per_km
        available_Wh = (
            None
            if level_frac is None
            else max(
                0.0,
                settings.battery_capacity_wh
                * max(0.0, level_frac - settings.energy_reserve_frac),
            )
        )

        est_range_km = self.range_model.estimate_range_km(
            capacity_Wh=settings.battery_capacity_wh,
            battery_level_frac=level_frac,
            cruise_power_W=settings.cruise_power_w,
            cruise_speed_mps=settings.cruise_speed_mps,
            reserve_frac=settings.energy_reserve_frac,
        )

        feasible = (est_range_km is not None) and (est_range_km >= distance_km)
        reason = "OK"
        if est_range_km is None:
            reason = "No battery level reading; cannot estimate range"
        elif not feasible:
            reason = f"Insufficient range. Need ~{distance_km:.2f} km, est range {est_range_km:.2f} km."

        return RangeEstimateResult(
            distance_km=distance_km,
            est_range_km=est_range_km,
            available_Wh=available_Wh,
            required_Wh=required_Wh,
            feasible=feasible,
            reason=reason,
        )

    async def fly_route_waypoints(
        self,
        waypoints: list[Coordinate],
        cruise_alt: float = 30.0,
        interpolate_steps: int = 6,
    ):
        """
        Fly a route defined by clicked map waypoints.
        - Drone starts from current/home location
        - Then flies to all specified waypoints
        - Returns home after last waypoint
        """

        if len(waypoints) < 2:
            raise ValueError("Need at least 2 waypoints (start & destination).")

        # Check if drone is connected and has home location
        if not hasattr(self.drone, "home_location") or self.drone.home_location is None:
            raise RuntimeError("Drone not connected or home location not available")

        # Get drone's home/current location
        from backend.utils.geo import _coord_from_home

        home_coord = _coord_from_home(self.drone.home_location)
        home_coord.alt = cruise_alt  # Set altitude for takeoff

        # normalize altitude for all waypoints
        route: list[Coordinate] = [home_coord]  # Start from drone's current location
        for w in waypoints:
            if getattr(w, "alt", None) is None:
                w.alt = cruise_alt
            route.append(w)

        # Add return to home as final point
        route.append(home_coord)

        start, dest = (
            route[0],
            route[-2],
        )  # Start from home, destination is last waypoint before returning home
        self._running = True

        # flight record
        if self._flight_id is None:
            self._flight_id = await self.repo.create_flight(
                start_lat=start.lat,
                start_lon=start.lon,
                start_alt=start.alt,
                dest_lat=dest.lat,
                dest_lon=dest.lon,
                dest_alt=dest.alt,
            )

        await self.repo.add_event(
            self._flight_id,
            "mission_created",
            {"alt": cruise_alt, "waypoints": len(waypoints)},
        )

        self._dest_coord = dest
        await asyncio.sleep(1.0)

        await self.repo.add_event(self._flight_id, "connected", {})

        # range check over full route (including return to home)
        from backend.config import settings

        preflight = await self._preflight_range_check_route(home_coord, waypoints)
        if not preflight.feasible and settings.enforce_preflight_range:
            raise RuntimeError(preflight.reason)

        await asyncio.to_thread(self.drone.arm_and_takeoff, cruise_alt)
        await self.repo.add_event(self._flight_id, "takeoff", {})

        # stitch segments; keep all anchors (starting from home -> waypoints -> home)
        path: list[Coordinate] = []
        for a, b in zip(route, route[1:]):
            seg = (
                list(self.maps.waypoints_between(a, b, steps=interpolate_steps))
                if interpolate_steps
                else [a, b]
            )
            if path and seg:
                seg = seg[1:]  # avoid duplicates
            path.extend(seg)

        await asyncio.to_thread(self.drone.follow_waypoints, path)
        await self.repo.add_event(self._flight_id, "reached_destination", {})

        # Wait for landing (RTL is already part of the path)
        await asyncio.to_thread(self.drone.wait_until_disarmed, 900)
        await self.repo.add_event(self._flight_id, "landed_home", {})
        await self.repo.finish_flight(
            self._flight_id,
            status="completed",
            note="Mission completed and returned home",
        )

    # In the run_waypoints method, ensure flight_id is set before starting tasks
    async def run_waypoints(self, waypoints: list[Coordinate], alt: float = 30.0):

        logger.info(f"🚁 Starting mission from {len(waypoints)} clicked waypoint(s)")

        # Start telemetry stream when mission begins
        try:
            from backend.messaging.websocket import telemetry_manager

            if not telemetry_manager._running:
                telemetry_manager.start_telemetry_stream()
                logger.info("Telemetry stream started for mission")
        except Exception as e:
            logger.warning(f"Could not start telemetry stream: {e}")

        if len(waypoints) < 2:
            raise ValueError("Need at least 2 waypoints (start & destination).")

        self._flight_id = None
        self._running = True

        # Store flight_id in instance variable for API access
        self._current_flight_data = {
            "waypoints": waypoints,
            "altitude": alt,
            "start_time": time.time(),
            "status": "initializing",
        }

        tasks: list[asyncio.Task] = []

        try:
            await self.opcua.start()
            await asyncio.to_thread(self.drone.connect)

            # Create flight record early so flight_id is available
            if self._flight_id is None:
                # Use first waypoint as start, last as destination
                start = waypoints[0]
                dest = waypoints[-1]
                self._flight_id = await self.repo.create_flight(
                    start_lat=start.lat,
                    start_lon=start.lon,
                    start_alt=alt,
                    dest_lat=dest.lat,
                    dest_lon=dest.lon,
                    dest_alt=alt,
                )
                logger.info(f"Created flight with ID: {self._flight_id}")

                # Update current flight data
                self._current_flight_data["flight_id"] = self._flight_id
                self._current_flight_data["status"] = "flight_created"

            tasks = [
                asyncio.create_task(self.heartbeat_task()),
                asyncio.create_task(self.telemetry_publish_task()),
                asyncio.create_task(self.mqtt_subscriber_task()),
                asyncio.create_task(self._raw_event_ingest_worker()),
                asyncio.create_task(self.video_health_monitor_task()),
            ]

            if self.video and hasattr(self, "vision_task"):
                tasks.append(asyncio.create_task(self.vision_task()))

            await asyncio.sleep(0.5)

            # Update status
            self._current_flight_data["status"] = "executing"
            await self.fly_route_waypoints(waypoints, cruise_alt=alt)

        except Exception:
            logger.exception("Mission failed in run_waypoints")
            self._current_flight_data["status"] = "failed"
            raise

        finally:
            self._running = False
            self._current_flight_data["status"] = "completed"
            await asyncio.sleep(0.5)

            for t in tasks:
                if t and not t.done():
                    t.cancel()
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass

            # Don't stop telemetry automatically - let API manage it
            # telemetry_manager.stop_telemetry_stream()

            self.drone.stop_dead_mans_switch()
            await self.opcua.stop()
            if self.video:
                self.video.close()
            self.drone.close()
            if self.publisher.is_running:
                self.publisher.stop()
