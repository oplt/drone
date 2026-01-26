import asyncio
import json
import time
import os
from .models import Coordinate
from .drone_base import DroneClient
from map.google_maps import GoogleMapsClient
from video.stream import DroneVideoStream
from analysis.llm import LLMAnalyzer
from telemetry.mqtt import MqttClient
from telemetry.opcua import DroneOpcUaServer
from db.repository import TelemetryRepository
from config import settings
from analysis.range_estimator import SimpleWhPerKmModel, RangeEstimateResult
from utils.geo import haversine_km, _coord_from_home, _total_mission_distance_km
from telemetry.publisher import TelemetryPublisher
from dronekit import VehicleMode
from drone.mavlink_drone import MavlinkDrone
from typing import Optional
import logging


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
        publisher: TelemetryPublisher,
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
        self.publisher = publisher
        self._telemetry_interval = settings.telem_log_interval_sec
        self._flight_id: Optional[int] = None
        self._ingest_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=2000)
        self._raw_event_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=2000)
        self._video_frame_queue: asyncio.Queue = asyncio.Queue(
            maxsize=10
        )  # Buffer only recent frames
        self._video_health_interval = 5.0  # Check video health every 5 seconds
        self.raspberry_camera = None
        self._frame_skip_count = 0  # Counter for frame skipping
        self._frames_to_skip = int(
            os.getenv("LLM_FRAME_SKIP", "2")
        )  # Process every Nth frame (default: every 3rd)

        if settings.raspberry_camera_enabled:
            try:
                from video.raspberry_camera import RaspberryCameraController

                self.raspberry_camera = RaspberryCameraController(
                    host=settings.rasperry_ip,
                    user=settings.rasperry_user,
                    key_path=settings.ssh_key_path,
                    script_path=settings.rasperry_streaming_script_path,
                    streaming_port=settings.rasperry_streaming_port,  # ← Streaming port
                )
                logging.info("✅ Raspberry Pi camera controller initialized")
            except ImportError as e:
                logging.warning(f"⚠️ Could not import RaspberryCameraController: {e}")
            except Exception as e:
                logging.error(f"❌ Failed to initialize Raspberry Pi camera: {e}")

    async def heartbeat_task(self):
        """Send regular heartbeats to keep the dead man's switch happy"""
        logging.info("Starting heartbeat task...")

        while self._running:
            try:
                # CRITICAL: Always update heartbeat timestamp if dead man's switch exists
                # This must happen BEFORE any conditions to ensure timestamp is always updated
                if hasattr(self.drone, "last_heartbeat"):
                    self.drone.last_heartbeat = time.time()
                    logging.debug(
                        f"Heartbeat timestamp updated: {self.drone.last_heartbeat}"
                    )

                # Also publish heartbeat status to MQTT for monitoring
                self.mqtt.publish(
                    "drone/heartbeat",
                    {"timestamp": time.time(), "status": "alive"},
                    qos=1,
                )  # QoS 1 for important heartbeat messages

                await asyncio.sleep(2.0)  # Send every 2 seconds
            except Exception as e:
                logging.error(f"⚠️  Error in heartbeat task: {e}")
                # Publish error but keep trying
                self.mqtt.publish(
                    "drone/errors",
                    {
                        "type": "heartbeat_error",
                        "message": str(e),
                        "timestamp": time.time(),
                    },
                )
                await asyncio.sleep(1.0)

    async def telemetry_publish_task(self):
        """Manage the telemetry publisher lifecycle"""
        try:
            # Start publisher in a thread (non-blocking)
            if not await asyncio.to_thread(self.publisher.start):
                logging.error("Failed to start telemetry publisher")
                return

            # Just keep this task alive while publisher runs
            while self._running and self.publisher.is_alive():
                await asyncio.sleep(1)

        except Exception as e:
            logging.error(f"Telemetry publisher error: {e}")
        finally:
            if self.publisher.is_running:
                await asyncio.to_thread(self.publisher.stop)

    async def video_health_monitor_task(self):
        """Monitor video stream health and publish status"""
        logging.info("Starting video health monitor task...")

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
                logging.error(f"Error in video health monitor: {e}")
                await asyncio.sleep(1.0)

    async def _telemetry_ingest_worker(self):
        """Persist compact telemetry frames derived from incoming MQTT mavlink messages."""
        BATCH_SIZE = 500
        FLUSH_INTERVAL = 0.5
        buffer = []
        last_flush = time.time()

        while self._running:
            try:
                try:
                    item = await asyncio.wait_for(
                        self._ingest_queue.get(), timeout=FLUSH_INTERVAL
                    )
                    buffer.append(item)
                    for _ in range(BATCH_SIZE - 1):
                        try:
                            buffer.append(self._ingest_queue.get_nowait())
                        except asyncio.QueueEmpty:
                            break
                except asyncio.TimeoutError:
                    pass

                if buffer and (
                    len(buffer) >= BATCH_SIZE
                    or (time.time() - last_flush) > FLUSH_INTERVAL
                ):
                    if self._flight_id:
                        inserted = await self.repo.add_telemetry_many_optimized(
                            self._flight_id, buffer
                        )
                        logging.debug(f"Inserted {inserted} telemetry rows")

                    for _ in range(len(buffer)):
                        self._ingest_queue.task_done()
                    buffer.clear()
                    last_flush = time.time()

            except Exception as e:
                logging.error(f"Error in telemetry ingest worker: {e}")
                buffer.clear()

    # In orchestrator.py, modify the ingest workers:
    async def _raw_event_ingest_worker(self):
        """OPTIMIZED: Process Mavlink events in larger batches"""
        BATCH_SIZE = 1000  # Increased from 500
        FLUSH_INTERVAL = 0.5  # Half second

        buffer = []
        last_flush = time.time()

        while self._running:
            try:
                # Try to get item with timeout
                try:
                    item = await asyncio.wait_for(
                        self._raw_event_queue.get(), timeout=FLUSH_INTERVAL
                    )
                    buffer.append(item)

                    # Fill buffer quickly
                    for _ in range(BATCH_SIZE - 1):
                        try:
                            buffer.append(self._raw_event_queue.get_nowait())
                        except asyncio.QueueEmpty:
                            break

                except asyncio.TimeoutError:
                    pass  # Time to flush buffer

                # Flush if buffer is full or timeout reached
                if buffer and (
                    len(buffer) >= BATCH_SIZE
                    or (time.time() - last_flush) > FLUSH_INTERVAL
                ):
                    if self._flight_id:
                        inserted = await self.repo.add_mavlink_events_many(
                            self._flight_id, buffer
                        )
                        logging.debug(f"Inserted {inserted} events")

                    # Clear buffer
                    for _ in range(len(buffer)):
                        self._raw_event_queue.task_done()
                    buffer.clear()
                    last_flush = time.time()

            except Exception as e:
                logging.error(f"Error in event worker: {e}")
                buffer.clear()

    async def mqtt_subscriber_task(self):
        """Listen for MQTT messages and handle them"""
        try:
            max_wait_time = 30.0  # Maximum seconds to wait for flight_id
            start_time = time.time()

            # Wait for flight_id with timeout
            while self._flight_id is None and self._running:
                elapsed = time.time() - start_time
                if elapsed > max_wait_time:
                    logging.error(
                        "Timeout waiting for flight_id in MQTT subscriber task"
                    )
                    return

                if elapsed > 5.0:  # Log warning after 5 seconds
                    logging.warning(f"Still waiting for flight_id... ({elapsed:.1f}s)")

                await asyncio.sleep(0.5)

            # Check exit conditions
            if not self._running:
                logging.info("MQTT subscriber task cancelled")
                return

            if self._flight_id is None:
                logging.error("Flight_id never set, MQTT subscriber exiting")
                return

            logging.info(f"Starting MQTT subscriber with flight_id: {self._flight_id}")

            # Attach queue so mqtt client can enqueue complete frames
            self.mqtt.attach_raw_event_queue(self._raw_event_queue)
            self.mqtt.attach_ingest_queue(self._ingest_queue)

            # Subscribe to command topics and set callback
            self.mqtt.client.subscribe("drone/commands/+", qos=1)
            self.mqtt.set_command_callback(self._handle_command)

            # Subscribe with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                if not self._running:
                    return

                try:
                    if await asyncio.to_thread(
                        self.mqtt.subscribe_to_topics, self._flight_id
                    ):
                        break
                    else:
                        if attempt < max_retries - 1:
                            logging.warning(
                                f"MQTT subscribe failed, retry {attempt + 1}/{max_retries}"
                            )
                            await asyncio.sleep(1.0)
                        else:
                            logging.error("All MQTT subscribe attempts failed")
                            return
                except Exception as e:
                    logging.error(f"MQTT subscribe error on attempt {attempt + 1}: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2.0)

            # Main loop with health checks
            while self._running:
                # Check if MQTT connection is still alive
                if hasattr(self.mqtt, "is_connected"):
                    if not await asyncio.to_thread(self.mqtt.is_connected):
                        logging.error(
                            "MQTT connection lost, attempting to reconnect..."
                        )
                        # Try to reconnect
                        if not await asyncio.to_thread(self.mqtt.reconnect):
                            logging.error("MQTT reconnection failed")
                            break

                # Sleep but check _running more frequently
                for _ in range(10):  # Check every 0.1 seconds instead of 1
                    if not self._running:
                        break
                    await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logging.info("MQTT subscriber task cancelled")
            raise
        except Exception as e:
            logging.error(f"Mqtt broker subscribe error: {e}")
        finally:
            logging.info("MQTT subscriber task cleaning up")
            # Cleanup code if needed

    def _handle_command(self, command_payload: dict):
        """Handle incoming command from MQTT (called from MQTT thread)"""
        command = command_payload.get("command")
        params = command_payload.get("params", {})

        if not command:
            logging.warning("Received command without command field")
            return

        logging.info(f"Received command: {command} with params: {params}")

        # Schedule command execution in async event loop
        if hasattr(self, "_command_queue"):
            try:
                self._command_queue.put_nowait((command, params))
            except Exception as e:
                logging.error(f"Error queuing command: {e}")

    async def command_handler_task(self):
        """Process commands from queue"""
        import asyncio

        self._command_queue = asyncio.Queue()

        while self._running:
            try:
                command, params = await asyncio.wait_for(
                    self._command_queue.get(), timeout=1.0
                )

                try:
                    await self._execute_command(command, params)
                except Exception as e:
                    logging.error(f"Error executing command {command}: {e}")
                    self.mqtt.publish(
                        "drone/command_error",
                        {"command": command, "error": str(e), "timestamp": time.time()},
                        qos=1,
                    )

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logging.error(f"Error in command handler task: {e}")
                await asyncio.sleep(1.0)

    async def _execute_command(self, command: str, params: dict):
        """Execute a drone command"""
        if not isinstance(self.drone, MavlinkDrone) or not self.drone.vehicle:
            logging.warning("Cannot execute command: drone not connected")
            return

        logging.info(f"Executing command: {command}")

        if command == "ARM":
            if not self.drone.vehicle.armed:
                self.drone.vehicle.mode = VehicleMode("GUIDED")
                self.drone.vehicle.armed = True
                if self._flight_id:
                    await self.repo.add_event(self._flight_id, "armed", {})
        elif command == "DISARM":
            if self.drone.vehicle.armed:
                self.drone.vehicle.armed = False
                if self._flight_id:
                    await self.repo.add_event(self._flight_id, "disarmed", {})
        elif command == "TAKEOFF":
            altitude = params.get("altitude", 10.0)
            await asyncio.to_thread(self.drone.arm_and_takeoff, altitude)
            (
                await self.repo.add_event(
                    self._flight_id, "takeoff", {"altitude": altitude}
                )
                if self._flight_id
                else None
            )
        elif command == "LAND":
            await asyncio.to_thread(self.drone.land)
            (
                await self.repo.add_event(self._flight_id, "land", {})
                if self._flight_id
                else None
            )
        elif command == "RTL":
            await asyncio.to_thread(self.drone.set_mode, "RTL")
            (
                await self.repo.add_event(self._flight_id, "rtl", {})
                if self._flight_id
                else None
            )
        elif command == "HOLD" or command == "LOITER":
            await asyncio.to_thread(self.drone.set_mode, "LOITER")
            (
                await self.repo.add_event(self._flight_id, "hold", {})
                if self._flight_id
                else None
            )
        elif command == "SET_MODE":
            mode = params.get("mode")
            if mode:
                await asyncio.to_thread(self.drone.set_mode, mode)
                (
                    await self.repo.add_event(
                        self._flight_id, "mode_change", {"mode": mode}
                    )
                    if self._flight_id
                    else None
                )
        elif command == "EMERGENCY_STOP":
            # Emergency stop - land immediately
            await asyncio.to_thread(self.drone.set_mode, "LAND")
            (
                await self.repo.add_event(self._flight_id, "emergency_stop", {})
                if self._flight_id
                else None
            )
            self.mqtt.publish(
                "drone/emergency",
                {
                    "type": "emergency_stop",
                    "message": "Emergency stop activated",
                    "timestamp": time.time(),
                },
                qos=2,
            )

        # Publish command acknowledgment
        self.mqtt.publish(
            "drone/command_ack",
            {"command": command, "status": "executed", "timestamp": time.time()},
            qos=1,
        )

    async def emergency_monitor_task(self):
        """Monitor for emergency conditions and handle them"""
        while self._running:
            try:
                # Check if dead man's switch was triggered
                if hasattr(self.drone, "dead_mans_switch_active"):
                    if not self.drone.dead_mans_switch_active and self.drone.vehicle:
                        # Dead man's switch was triggered!
                        logging.critical(
                            "🚨 DEAD MAN'S SWITCH TRIGGERED - Emergency RTL initiated"
                        )
                        self.mqtt.publish(
                            "drone/emergency",
                            {
                                "type": "dead_mans_switch_triggered",
                                "message": "Connection lost - drone executing emergency protocol",
                                "timestamp": time.time(),
                            },
                            qos=2,
                        )  # QoS 2 for critical emergency messages

                        # Log emergency event
                        if self._flight_id:
                            await self.repo.add_event(
                                self._flight_id,
                                "emergency_rtl",
                                {"reason": "dead_mans_switch_triggered"},
                            )

                        # Stop all other operations
                        self._running = False
                        break
                await asyncio.sleep(1.0)
            except Exception as e:
                logging.error(f"Error in emergency monitor: {e}")
                await asyncio.sleep(1.0)

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
            logging.info(f"Created flight with ID: {self._flight_id}")

        await self.repo.add_event(
            self._flight_id, "mission_created", {"alt": cruise_alt}
        )

        self._dest_coord = dest

        await asyncio.sleep(1.0)

        await self.repo.add_event(self._flight_id, "connected", {})

        # Preflight range check (can hard-fail if you want)
        home = _coord_from_home(self.drone.home_location)

        preflight = await self._preflight_range_check(home, start, dest)
        if not preflight.feasible and settings.ENFORCE_PREFLIGHT_RANGE:
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

    def _estimate_range(
        self, distance_km: float, battery_level_frac: float | None
    ) -> RangeEstimateResult:
        est_range_km = self.range_model.estimate_range_km(
            capacity_Wh=settings.battery_capacity_wh,
            battery_level_frac=battery_level_frac,
            cruise_power_W=settings.cruise_power_w,
            cruise_speed_mps=settings.cruise_speed_mps,
            reserve_frac=settings.energy_reserve_frac,
        )
        note = ""
        feasible = False
        req_Wh = None
        avail_Wh = None
        if est_range_km is None:
            note = "No battery level reading; cannot estimate range (fail safe)."
        else:
            feasible = est_range_km >= distance_km
            v_kmh = settings.cruise_speed_mps * 3.6
            wh_per_km = settings.cruise_power_w / v_kmh
            req_Wh = wh_per_km * distance_km
            avail_Wh = settings.battery_capacity_wh * max(
                0.0, (battery_level_frac or 0.0) - settings.energy_reserve_frac
            )
            if not feasible:
                note = f"Insufficient range. Need ~{distance_km:.2f} km, est range {est_range_km:.2f} km."
            else:
                note = (
                    f"OK: dist {distance_km:.2f} km ≤ est range {est_range_km:.2f} km."
                )
        return RangeEstimateResult(
            distance_km, est_range_km, avail_Wh, req_Wh, feasible, note
        )

    async def _preflight_range_check(
        self, home: Coordinate, start: Coordinate, dest: Coordinate
    ) -> RangeEstimateResult:
        """
        Uses total route distance: home→start→dest→home.
        Assumes self.drone.connect() was already called so home_location is set.
        """
        # # 1) Build coordinates
        # home = _coord_from_home(self.drone.home_location)

        # 2) Total mission distance (km)
        distance_km = _total_mission_distance_km(home, start, dest)

        # 3) Inputs for range model
        t = self.drone.get_telemetry()
        level_frac = (
            None
            if t.battery_remaining is None
            else max(0.0, min(1.0, float(t.battery_remaining) / 100.0))
        )

        capacity_Wh = settings.battery_capacity_wh
        cruise_power_W = settings.cruise_power_w
        cruise_speed_mps = settings.cruise_speed_mps
        reserve_frac = settings.energy_reserve_frac

        model = SimpleWhPerKmModel()
        est_range_km = model.estimate_range_km(
            capacity_Wh=capacity_Wh,
            battery_level_frac=level_frac,
            cruise_power_W=cruise_power_W,
            cruise_speed_mps=cruise_speed_mps,
            reserve_frac=reserve_frac,
        )

        # 4) Required energy vs. available (for a clear reason message)
        v_kmh = max(0.1, cruise_speed_mps * 3.6)
        wh_per_km = cruise_power_W / v_kmh
        required_Wh = distance_km * wh_per_km
        available_Wh = (
            None
            if level_frac is None
            else max(0.0, capacity_Wh * max(0.0, level_frac - reserve_frac))
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

    async def _range_guard_task(self):
        """Re-evaluate remaining distance periodically and warn if we're going to run short."""
        while self._running:
            try:
                if self._dest_coord:
                    t = self.drone.get_telemetry()
                    remain_km = haversine_km(
                        t.lat, t.lon, self._dest_coord.lat, self._dest_coord.lon
                    )
                    level = None
                    if t.battery_current is not None:
                        level = max(0.0, min(1.0, float(t.battery_current) / 100.0))
                    res = self._estimate_range(remain_km, level)
                    await self.opcua.update_range(
                        res.est_range_km or 0.0, res.feasible, res.reason
                    )
                    if not res.feasible:
                        self.mqtt.publish(
                            "drone/warnings",
                            {
                                "type": "inflight_range_warning",
                                "remaining_distance_km": remain_km,
                                "est_range_km": res.est_range_km,
                                "note": res.reason,
                            },
                        )
            except Exception:
                logging.info("CANNOT APPLY _range_guard_task")

            await asyncio.sleep(2.0)  # evaluation interval

    async def _video_frame_reader_task(self):
        """Async frame reader that reads frames one at a time and queues them"""
        logging.info("Starting async video frame reader...")

        if not self.video:
            logging.warning("No video stream available for frame reading")
            return

        try:
            # Read frames one at a time asynchronously
            for _, frame in self.video.frames():
                if not self._running:
                    break

                # Non-blocking queue put - drop oldest frame if queue is full
                try:
                    self._video_frame_queue.put_nowait(frame)
                except asyncio.QueueFull:
                    # Drop oldest frame to maintain recency
                    try:
                        self._video_frame_queue.get_nowait()
                        self._video_frame_queue.task_done()
                        logging.debug(
                            "Dropped old frame to maintain real-time processing"
                        )
                    except asyncio.QueueEmpty:
                        pass
                    # Try again to add new frame
                    try:
                        self._video_frame_queue.put_nowait(frame)
                    except asyncio.QueueFull:
                        logging.warning(
                            "Frame queue still full after dropping oldest frame"
                        )

                # Small sleep to yield control and prevent tight loop
                await asyncio.sleep(0.001)  # 1ms yield

        except Exception as e:
            logging.error(f"Error in video frame reader: {e}")
            self.mqtt.publish(
                "drone/events",
                {
                    "level": "error",
                    "msg": f"Video frame reader error: {str(e)}",
                    "timestamp": time.time(),
                },
                qos=1,
            )

    async def vision_task(self):
        """Process video frames for object detection and analysis (non-blocking)"""
        logging.info("Starting vision task for drone video analysis...")

        if not self.video:
            logging.warning("No video stream available, skipping vision task")
            return

        try:
            # Start frame reader task
            frame_reader_task = asyncio.create_task(
                self._video_frame_reader_task(), name="video_frame_reader"
            )

            # Process frames from queue with skipping
            while self._running:
                try:
                    # Get frame with timeout to allow periodic checks
                    frame = await asyncio.wait_for(
                        self._video_frame_queue.get(), timeout=1.0
                    )

                    # Frame skipping: only process every Nth frame to reduce LLM API calls
                    self._frame_skip_count += 1
                    if self._frame_skip_count < self._frames_to_skip:
                        # Skip this frame, mark as done and continue
                        self._video_frame_queue.task_done()
                        continue

                    # Reset counter and process this frame
                    self._frame_skip_count = 0

                    # Process frame for object detection (with circuit breaker protection)
                    # detect_objects now returns [] on error instead of raising, so no try/except needed
                    dets = await self.analyzer.detect_objects(frame)
                    payload = [d.__dict__ for d in dets]

                    # Publish detections to MQTT (skip empty detections when circuit breaker is open)
                    # Only publish if we have detections or circuit breaker is closed
                    if (
                        payload
                        or not hasattr(self.analyzer, "_circuit_open")
                        or not self.analyzer._circuit_open
                    ):
                        self.mqtt.publish("drone/detections", payload, qos=0)
                    # Skip publishing empty arrays when circuit breaker is open to reduce spam

                    # Update OPC UA with detection data (if available)
                    if self.opcua and payload:  # Only update if we have detections
                        try:
                            await self.opcua.update_detections(json.dumps(payload))
                        except Exception as e:
                            logging.debug(f"OPC UA update failed: {e}")

                    # Log detection events if significant objects found
                    if dets:
                        logging.info(f"Detected {len(dets)} objects in video frame")
                        if self._flight_id:
                            await self.repo.add_event(
                                self._flight_id,
                                "object_detected",
                                {
                                    "count": len(dets),
                                    "objects": [d.__dict__ for d in dets],
                                },
                            )

                    # Mark frame as processed
                    self._video_frame_queue.task_done()

                except asyncio.TimeoutError:
                    # No frame available, continue loop to check _running
                    continue
                except Exception as e:
                    logging.error(f"Error processing frame: {e}")
                    # Mark task as done even on error to prevent queue blocking
                    try:
                        self._video_frame_queue.task_done()
                    except ValueError:
                        pass  # Already done or not in queue
                    continue

            # Cancel frame reader when vision task stops
            if not frame_reader_task.done():
                frame_reader_task.cancel()
                try:
                    await frame_reader_task
                except asyncio.CancelledError:
                    pass

        except RuntimeError as e:
            error_msg = f"Video processing error: {str(e)}"
            logging.error(error_msg)
            self.mqtt.publish(
                "drone/events",
                {"level": "error", "msg": error_msg, "timestamp": time.time()},
                qos=1,
            )
        except Exception as e:
            error_msg = f"Unexpected error in vision task: {str(e)}"
            logging.error(error_msg)
            self.mqtt.publish(
                "drone/events",
                {"level": "error", "msg": error_msg, "timestamp": time.time()},
                qos=1,
            )

    async def raspberry_camera_task(self):
        """Main task to manage Raspberry Pi camera lifecycle"""
        logging.info("🎥 Starting Raspberry Pi camera manager...")

        last_connection_state = False
        camera_start_attempted = False

        while self._running:
            try:
                # Check if drone is connected
                is_connected = await asyncio.to_thread(self.drone.is_connected)

                # Connection state changed
                if is_connected != last_connection_state:
                    if is_connected:
                        logging.info(
                            "🚀 Drone connected, checking Raspberry Pi camera..."
                        )
                    else:
                        logging.info("📴 Drone disconnected")
                        camera_start_attempted = False
                    last_connection_state = is_connected

                if is_connected and self.raspberry_camera:
                    # Start camera if not already streaming and not attempted yet
                    if (
                        not self.raspberry_camera.is_streaming
                        and not camera_start_attempted
                    ):
                        logging.info("🎬 Starting Raspberry Pi camera...")

                        # Start camera streaming
                        success = await self.raspberry_camera.start_streaming()
                        camera_start_attempted = True

                        if success:
                            # Update video source to use Raspberry Pi stream
                            stream_url = await self.raspberry_camera.get_stream_url()

                            # Reinitialize video with Raspberry Pi stream
                            if self.video:
                                try:
                                    self.video.close()
                                except Exception as e:
                                    logging.debug(
                                        f"Error closing old video stream: {e}"
                                    )

                            # Create new video stream with retry logic
                            max_retries = 3
                            retry_delay = 2.0
                            video_initialized = False

                            for attempt in range(max_retries):
                                try:
                                    logging.info(
                                        f"Initializing video stream (attempt {attempt + 1}/{max_retries})..."
                                    )
                                    self.video = DroneVideoStream(
                                        source=stream_url,
                                        width=settings.drone_video_width,
                                        height=settings.drone_video_height,
                                        fps=settings.drone_video_fps,
                                        open_timeout_s=10.0,  # Longer timeout for network stream
                                        enable_recording=settings.drone_video_save_stream,
                                        recording_path=settings.drone_video_save_path,
                                    )
                                    video_initialized = True
                                    break
                                except Exception as e:
                                    logging.warning(
                                        f"Video stream initialization attempt {attempt + 1} failed: {e}"
                                    )
                                    if attempt < max_retries - 1:
                                        logging.info(
                                            f"Retrying in {retry_delay} seconds..."
                                        )
                                        await asyncio.sleep(retry_delay)

                            if not video_initialized:
                                logging.error(
                                    "Failed to initialize video stream after all retries"
                                )
                                continue

                            logging.info(
                                f"📹 Switched to Raspberry Pi camera stream: {stream_url}"
                            )

                            # Start vision task
                            asyncio.create_task(self.vision_task(), name="vision_task")
                        else:
                            logging.error("❌ Failed to start Raspberry Pi camera")
                            # Retry after delay
                            await asyncio.sleep(10)
                            camera_start_attempted = False
                    else:
                        # Camera is already streaming or we attempted, check health periodically
                        if self.raspberry_camera.is_streaming:
                            # Check health every 10 seconds
                            if await self.raspberry_camera.check_health():
                                # Camera is healthy, nothing to do
                                pass
                            else:
                                logging.warning(
                                    "⚠️ Raspberry Pi camera stream unhealthy"
                                )
                                # Try to restart
                                await self.raspberry_camera.stop_streaming()
                                camera_start_attempted = False
                elif not is_connected and self.raspberry_camera:
                    # Drone disconnected, ensure camera is stopped
                    if self.raspberry_camera.is_streaming:
                        logging.info(
                            "📴 Drone disconnected, stopping Raspberry Pi camera..."
                        )
                        await self.raspberry_camera.stop_streaming()
                        camera_start_attempted = False

                await asyncio.sleep(2)  # Check every 2 seconds

            except Exception as e:
                logging.error(f"Raspberry camera task error: {e}")
                camera_start_attempted = False
                await asyncio.sleep(5)  # Longer delay on error

    async def run(self, start: Coordinate, dest: Coordinate, alt=30.0):
        """Run flight task with direct coordinates (no geocoding needed)"""

        logging.info(
            f"🚁 Starting safe flight from ({start.lat}, {start.lon}) to ({dest.lat}, {dest.lon})"
        )

        # Set event loop for MQTT client early to enable message buffering
        self.mqtt.set_event_loop(asyncio.get_running_loop())

        # Ensure altitude is set
        start.alt = alt
        dest.alt = alt

        # Get user_id from environment if set (from Flask dashboard)
        user_id = None
        user_id_str = os.getenv("FLIGHT_USER_ID")
        if user_id_str:
            try:
                user_id = int(user_id_str)
            except (ValueError, TypeError):
                logging.warning(f"Invalid FLIGHT_USER_ID: {user_id_str}")

        # Create flight record early to set flight_id before connecting
        flight_id = await self.repo.create_flight(
            start_lat=start.lat,
            start_lon=start.lon,
            start_alt=start.alt,
            dest_lat=dest.lat,
            dest_lon=dest.lon,
            dest_alt=dest.alt,
            user_id=user_id,
        )

        self._flight_id = flight_id
        logging.info(f"✅ Created flight with ID: {self._flight_id}")
        if self._flight_id:
            await self.repo.add_event(
                self._flight_id,
                "flight_created",
                {
                    "alt": alt,
                    "start": f"({start.lat}, {start.lon})",
                    "end": f"({dest.lat}, {dest.lon})",
                },
            )

        # Start OPC UA server so publisher updates have variables to write to
        try:
            await self.opcua.start()
        except Exception as e:
            logging.error(f"Failed to start OPC UA server: {e}")

        # Connect to drone with error handling
        try:
            connection_str = (
                self.drone.connection_str
                if isinstance(self.drone, MavlinkDrone)
                else "unknown"
            )
            logging.info(f"Connecting to drone at: {connection_str}")
            await asyncio.to_thread(self.drone.connect)
            logging.info("✅ Drone connection established successfully")
        except Exception as e:
            error_msg = f"❌ Failed to connect to drone: {e}"
            logging.error(error_msg, exc_info=True)
            # Update flight status to failed
            if self._flight_id:
                await self.repo.finish_flight(
                    self._flight_id,
                    status="failed",
                    note=f"Connection failed: {str(e)}",
                )
            raise ConnectionError(error_msg) from e

        # Start all tasks including the critical heartbeat task
        tasks = [
            asyncio.create_task(
                self.heartbeat_task(), name="heartbeat_task"
            ),  # CRITICAL SAFETY TASK
            asyncio.create_task(
                self.telemetry_publish_task(), name="telemetry_publish_task"
            ),  # MAVLink -> MQTT forwarder (SITL/MAVProxy)
            asyncio.create_task(
                self.mqtt_subscriber_task(), name="mqtt_subscriber_task"
            ),  # subscribes to mqtt broker and saves to db
            asyncio.create_task(
                self._raw_event_ingest_worker(), name="raw_event_ingest_worker"
            ),
            asyncio.create_task(
                self._telemetry_ingest_worker(), name="telemetry_ingest_worker"
            ),
            asyncio.create_task(
                self.command_handler_task(), name="command_handler_task"
            ),  # Handle commands from dashboard
            # asyncio.create_task(self.video_health_monitor_task()),  # Monitor video stream health
            # asyncio.create_task(self.vision_task()),  # Process video for object detection - started by raspberry_camera_task
            # asyncio.create_task(self._range_guard_task()),
            asyncio.create_task(
                self.emergency_monitor_task(), name="emergency_monitor_task"
            ),
        ]

        # Add Raspberry Pi camera task if enabled
        if self.raspberry_camera:
            tasks.append(
                asyncio.create_task(
                    self.raspberry_camera_task(), name="raspberry_camera_task"
                )
            )

        try:
            logging.info("Background tasks started, beginning flight...")
            await self.fly_route(start, dest, cruise_alt=alt)

        except Exception as e:
            logging.info(f"❌ Flight error: {e}")
            raise
        finally:
            logging.info("🛑 Shutting down flight operations...")
            self._running = False

            # Stop Raspberry Pi camera
            if self.raspberry_camera and self.raspberry_camera.is_streaming:
                await self.raspberry_camera.stop_streaming()

            if tasks:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

            # Safely stop the dead man's switch
            if isinstance(self.drone, MavlinkDrone):
                self.drone.stop_dead_mans_switch()

            # Stop OPC UA server if available
            if self.opcua:
                try:
                    await self.opcua.stop()
                except Exception as e:
                    logging.error(f"Error stopping OPC UA server: {e}")
            # Close video stream properly
            if self.video:
                self.video.close()
            self.drone.close()

            if self.publisher.is_running:
                logging.info("Stopping telemetry publisher...")
                self.publisher.stop()

            logging.info("✅ Safe shutdown completed")
