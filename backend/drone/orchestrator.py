import asyncio, json, time
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
from backend.utils.geo import haversine_km, _coord_from_home, _total_mission_distance_km
from backend.utils.telemetry_publisher_sim import ArduPilotTelemetryPublisher
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


    async def heartbeat_task(self):
        """Send regular heartbeats to keep the dead man's switch happy"""
        logging.info("Starting heartbeat task...")

        while True:
            try:
                '''
                MODIFY PUBLISH TOPIC BEFORE DRONE TEST CONNECTION !!!
                '''
                # Also publish heartbeat status to MQTT for monitoring
                self.mqtt.publish("drone/heartbeat", {
                                                                "timestamp": time.time(),
                                                                "status": "alive"
                                                            }, qos=1)  # QoS 1 for important heartbeat messages
                await asyncio.sleep(2.0)  # Send every 2 seconds
            except Exception as e:
                logging.info(f"⚠️  Error in heartbeat task: {e}")
                # print(f"⚠️  Error in heartbeat task: {e}")
                # Publish error but keep trying
                self.mqtt.publish("drone/errors", {
                                        "type": "heartbeat_error",
                                        "message": str(e),
                                        "timestamp": time.time()
                                    })
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
                    self.mqtt.publish("drone/video/status", {
                        "timestamp": time.time(),
                        "healthy": status["healthy"],
                        "frame_count": status["frame_count"],
                        "fps": status["fps"],
                        "resolution": status["resolution"],
                        "recording": status["recording"],
                        "recording_file": status["recording_file"]
                    }, qos=1)
                    
                    # Update OPC UA with video status
                    await self.opcua.update_video_status(
                        healthy=status["healthy"],
                        fps=status["fps"],
                        recording=status["recording"]
                    )
                    
                    # Log warnings if video is unhealthy
                    if not status["healthy"]:
                        logging.warning("Video stream is unhealthy")
                        self.mqtt.publish("drone/warnings", {
                            "type": "video_stream_unhealthy",
                            "message": "Video stream connection issues detected",
                            "timestamp": time.time()
                        }, qos=1)
                
                await asyncio.sleep(self._video_health_interval)
                
            except Exception as e:
                logging.error(f"Error in video health monitor: {e}")
                await asyncio.sleep(1.0)


    # async def _telemetry_ingest_worker(self):
    #     """Drain MQTT-parsed rows and bulk-insert. Small batches, frequent commits."""
    #     BATCH_SIZE = 200
    #     INTERVAL_S = 0.25
    #     buffer = []
    #     while self._running:
    #         try:
    #             item = await asyncio.wait_for(self._ingest_queue.get(), timeout=INTERVAL_S)
    #             buffer.append(item)
    #             # try to coalesce up to BATCH_SIZE quickly
    #             for _ in range(BATCH_SIZE-1):
    #                 try:
    #                     buffer.append(self._ingest_queue.get_nowait())
    #                 except asyncio.QueueEmpty:
    #                     break
    #             if buffer:
    #                 # strip flight_id from rows; repo will set it if you prefer
    #                 await self.repo.add_telemetry_many(self._flight_id, buffer)
    #                 for _ in buffer:
    #                     self._ingest_queue.task_done()
    #                 buffer.clear()
    #         except asyncio.TimeoutError:
    #             if buffer:
    #                 await self.repo.add_telemetry_many(self._flight_id, buffer)
    #                 for _ in buffer:
    #                     self._ingest_queue.task_done()
    #                 buffer.clear()
    #         except Exception as e:
    #             # log and continue
    #             buffer.clear()
    #


    async def _raw_event_ingest_worker(self):
        """Drain raw MAVLink events from MQTT and bulk-insert into MavlinkEvent."""
        BATCH_SIZE = 500
        INTERVAL_S = 0.25
        buffer = []
        logging.info("Starting _raw_event_ingest_worker")
        
        # while self._running:
        while True:
            try:
                item = await asyncio.wait_for(self._raw_event_queue.get(), timeout=INTERVAL_S)
                logging.debug(f"Received item from queue: {item.get('msg_type', 'UNKNOWN')}")
                buffer.append(item)
                # coalesce quickly
                for _ in range(BATCH_SIZE-1):
                    try:
                        buffer.append(self._raw_event_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                if buffer:
                    if self._flight_id is None:
                        logging.warning("Flight ID is None, cannot save MavlinkEvent data")
                        buffer.clear()
                        continue
                    
                    logging.info(f"Processing batch of {len(buffer)} events for flight {self._flight_id}")
                    try:
                        inserted_count = await self.repo.add_mavlink_events_many(self._flight_id, buffer)
                        logging.info(f"Inserted {inserted_count} MavlinkEvent records")
                    except Exception as e:
                        logging.error(f"Failed to insert MavlinkEvent data: {e}")
                    
                    for _ in buffer:
                        self._raw_event_queue.task_done()
                    buffer.clear()
            except asyncio.TimeoutError:
                if buffer:
                    if self._flight_id is None:
                        logging.warning("Flight ID is None, cannot save MavlinkEvent data")
                        buffer.clear()
                        continue
                    
                    logging.info(f"Timeout flush: processing {len(buffer)} events for flight {self._flight_id}")
                    try:
                        inserted_count = await self.repo.add_mavlink_events_many(self._flight_id, buffer)
                        logging.info(f"Inserted {inserted_count} MavlinkEvent records (timeout flush)")
                    except Exception as e:
                        logging.error(f"Failed to insert MavlinkEvent data (timeout flush): {e}")
                    
                    for _ in buffer:
                        self._raw_event_queue.task_done()
                    buffer.clear()
            except Exception as e:
                logging.error(f"Error in _raw_event_ingest_worker: {e}")
                buffer.clear()


    async def mqtt_subscriber_task(self):
        """Listen for MQTT messages and handle them"""
        try:
            # Wait for flight_id to be set
            while self._flight_id is None:
                logging.info("Waiting for flight_id to be set before starting MQTT subscriber...")
                await asyncio.sleep(0.5)
            
            logging.info(f"Starting MQTT subscriber with flight_id: {self._flight_id}")
            
            # Attach queue so mqtt client can enqueue complete frames
            # self.mqtt.attach_ingest_queue(self._ingest_queue)
            self.mqtt.attach_raw_event_queue(self._raw_event_queue)

            if not await asyncio.to_thread(self.mqtt.subscribe_to_topics, self._flight_id):
                logging.error("Failed to start MQTT subscriber")
                while self._running:
                    await asyncio.sleep(1)

            logging.info("MQTT subscriber started and listening for messages")
            # Keep alive
            while self._running:
                await asyncio.sleep(1)
        except Exception as e:
            logging.error(f"Mqtt broker subscribe error: {e}")


    async def emergency_monitor_task(self):
        """Monitor for emergency conditions and handle them"""
        while self._running:
            try:
                # Check if dead man's switch was triggered
                if hasattr(self.drone, 'dead_mans_switch_active'):
                    if not self.drone.dead_mans_switch_active and self.drone.vehicle:
                        # Dead man's switch was triggered!
                        self.mqtt.publish("drone/emergency", {
                            "type": "dead_mans_switch_triggered",
                            "message": "Connection lost - drone executing emergency protocol",
                            "timestamp": time.time()
                        }, qos=2)  # QoS 2 for critical emergency messages

                        # Stop all other operations
                        self._running = False
                        break
                await asyncio.sleep(1.0)
            except Exception as e:
                logging.info(f"Error in emergency monitor: {e}")
                # print(f"Error in emergency monitor: {e}")
                await asyncio.sleep(1.0)

    async def fly_route(self, start, dest, cruise_alt=30.0):
        # start = await asyncio.to_thread(self.maps.geocode, start_addr); start.alt = cruise_alt
        # dest  = await asyncio.to_thread(self.maps.geocode, end_addr); dest.alt = cruise_alt
        self._running = True
        
        # Create flight record if not already created
        if self._flight_id is None:
            self._flight_id = await self.repo.create_flight(
                start_lat=start.lat, start_lon=start.lon, start_alt=start.alt,
                dest_lat=dest.lat,   dest_lon=dest.lon,   dest_alt=dest.alt,
            )
            logging.info(f"Created flight with ID: {self._flight_id}")
        
        await self.repo.add_event(self._flight_id, "mission_created", {"alt": cruise_alt})

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
        await self.repo.finish_flight(self._flight_id, status="completed", note="RTL to home completed")


    def _estimate_range(self, distance_km: float, battery_level_frac: float | None) -> RangeEstimateResult:
        est_range_km = self.range_model.estimate_range_km(
            capacity_Wh=settings.battery_capacity_wh,
            battery_level_frac=battery_level_frac,
            cruise_power_W=settings.cruise_power_w,
            cruise_speed_mps=settings.cruise_speed_mps,
            reserve_frac=settings.energy_reserve_frac
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
            avail_Wh = settings.battery_capacity_wh * max(0.0, (battery_level_frac or 0.0) - settings.energy_reserve_frac)
            if not feasible:
                note = f"Insufficient range. Need ~{distance_km:.2f} km, est range {est_range_km:.2f} km."
            else:
                note = f"OK: dist {distance_km:.2f} km ≤ est range {est_range_km:.2f} km."
        return RangeEstimateResult(distance_km, est_range_km, avail_Wh, req_Wh, feasible, note)



    async def _preflight_range_check(self, home: Coordinate, start: Coordinate, dest: Coordinate) -> RangeEstimateResult:
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
        level_frac = None if t.battery_remaining is None else max(0.0, min(1.0, float(t.battery_remaining) / 100.0))

        capacity_Wh     = settings.battery_capacity_wh
        cruise_power_W  = settings.cruise_power_w
        cruise_speed_mps= settings.cruise_speed_mps
        reserve_frac    = settings.energy_reserve_frac

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
        available_Wh = None if level_frac is None else max(0.0, capacity_Wh * max(0.0, level_frac - reserve_frac))

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
                    remain_km = haversine_km(t.lat, t.lon, self._dest_coord.lat, self._dest_coord.lon)
                    level = None
                    if t.battery_current is not None:
                        level = max(0.0, min(1.0, float(t.battery_current) / 100.0))
                    res = self._estimate_range(remain_km, level)
                    await self.opcua.update_range(res.est_range_km or 0.0, res.feasible, res.reason)
                    if not res.feasible:
                        self.mqtt.publish("drone/warnings", {
                            "type": "inflight_range_warning",
                            "remaining_distance_km": remain_km,
                            "est_range_km": res.est_range_km,
                            "note": res.reason
                        })
                        # Optional: trigger RTL or hold
                        # self.drone.set_mode("RTL")
            except Exception:
                logging.info(f"CANNOT APPLY _range_guard_task")

            await asyncio.sleep(2.0)  # evaluation interval


    async def vision_task(self):
        """Process video frames for object detection and analysis"""
        logging.info("Starting vision task for drone video analysis...")

        try:
            for _, frame in self.video.frames():
                if not self._running:
                    break
                    
                # Process frame for object detection
                dets = await self.analyzer.detect_objects(frame)
                payload = [d.__dict__ for d in dets]
                
                # Publish detections to MQTT
                self.mqtt.publish("drone/detections", payload, qos=0)
                
                # Update OPC UA with detection data
                await self.opcua.update_detections(json.dumps(payload))
                
                # Log detection events if significant objects found
                if dets:
                    logging.info(f"Detected {len(dets)} objects in video frame")
                    await self.repo.add_event(self._flight_id, "object_detected", {
                        "count": len(dets),
                        "objects": [d.__dict__ for d in dets]
                    })
                
                await asyncio.sleep(0)  # yield control
                
        except RuntimeError as e:
            error_msg = f"Video processing error: {str(e)}"
            logging.error(error_msg)
            self.mqtt.publish("drone/events", {
                "level": "error",
                "msg": error_msg,
                "timestamp": time.time()
            }, qos=1)
        except Exception as e:
            error_msg = f"Unexpected error in vision task: {str(e)}"
            logging.error(error_msg)
            self.mqtt.publish("drone/events", {
                "level": "error", 
                "msg": error_msg,
                "timestamp": time.time()
            }, qos=1)

    async def run(self, start_addr: str, end_addr: str, alt=30.0):
        logging.info(f"🚁 Starting safe flight from {start_addr} to {end_addr}")
        start = await asyncio.to_thread(self.maps.geocode, start_addr); start.alt = alt
        dest  = await asyncio.to_thread(self.maps.geocode, end_addr); dest.alt = alt

        self._flight_id = await self.repo.create_flight(
            start_lat=start.lat, start_lon=start.lon, start_alt=start.alt,
            dest_lat=dest.lat,   dest_lon=dest.lon,   dest_alt=dest.alt,
        )

        await self.opcua.start()
        # self.drone.connect()
        await asyncio.to_thread(self.drone.connect)

        # Start all tasks including the critical heartbeat task
        tasks = [
            asyncio.create_task(self.heartbeat_task()),  # CRITICAL SAFETY TASK
            asyncio.create_task(self.telemetry_publish_task()), # Publish telemetry to MQTT and should be deleted before drone connection
            asyncio.create_task(self.mqtt_subscriber_task()), # subscribes to mqtt broker and saves to db
            asyncio.create_task(self._raw_event_ingest_worker()),
            # asyncio.create_task(self._telemetry_ingest_worker()),
            asyncio.create_task(self.video_health_monitor_task()),  # Monitor video stream health
            asyncio.create_task(self.vision_task()),  # Process video for object detection
            # asyncio.create_task(self._range_guard_task()),
            # asyncio.create_task(self.emergency_monitor_task()),
        ]

        try:
            logging.info("Background tasks started, beginning flight...")
            await self.fly_route(start, dest, cruise_alt=alt)

        except Exception as e:
            logging.info(f"❌ Flight error: {e}")
            raise
        finally:
            logging.info("🛑 Shutting down flight operations...")
            # print("🛑 Shutting down flight operations...")
            self._running = False
            await asyncio.sleep(0.5)  # Give tasks time to see the flag



            # Cancel all tasks
            for task in tasks:
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            # Safely stop the dead man's switch
            self.drone.stop_dead_mans_switch()

            await self.opcua.stop()
            # Close video stream properly
            if self.video:
                self.video.close()
            self.drone.close()

            if self.publisher.is_running:
                # print("Stopping telemetry publisher...")
                logging.info("Stopping telemetry publisher...")
                self.publisher.stop()

            # print("✅ Safe shutdown completed")
            logging.info("✅ Safe shutdown completed")

