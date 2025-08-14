import asyncio, json, time
from typing import Iterable
from .models import Coordinate
from .drone_base import DroneClient
from map.google_maps import GoogleMapsClient
from video.stream import VideoStream
from analysis.llm import LLMAnalyzer
from messaging.mqtt import MqttClient
from messaging.opcua import DroneOpcUaServer
from db.repository import TelemetryRepository
from config import settings
from analysis.range_estimator import SimpleWhPerKmModel, RangeEstimateResult
from utils.geo import haversine_km, _coord_from_home, _total_mission_distance_km
from utils.telemetry_publisher_sim import ArduPilotTelemetryPublisher
import contextlib
import logging

logging.basicConfig(
                    level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[
                        logging.FileHandler("drone.log"),
                        logging.StreamHandler()  # still print to console
                    ]
                )


class Orchestrator:
    def __init__(
            self,
            drone: DroneClient,
            maps: GoogleMapsClient,
            analyzer: LLMAnalyzer,
            mqtt: MqttClient,
            opcua: DroneOpcUaServer,
            # video: VideoStream,
            telemetry_repo: TelemetryRepository,
            publisher: ArduPilotTelemetryPublisher
    ):
        self.drone = drone
        self.maps = maps
        self.analyzer = analyzer
        self.mqtt = mqtt
        self.opcua = opcua
        # self.video = video
        self.repo = telemetry_repo
        self.range_model = SimpleWhPerKmModel()
        self._running = True
        self._dest_coord: Coordinate | None = None
        # self._heartbeat_task = None
        self.publisher = publisher
        self._telemetry_interval = settings.telem_log_interval_sec


    async def heartbeat_task(self):
        """Send regular heartbeats to keep the dead man's switch happy"""
        logging.info("Starting heartbeat task...")
        # print("Starting heartbeat task...")
        while self._running:
            try:
                # self.drone.send_heartbeat()

                '''
                CONTROL PUBLISH ENDPOINT BEFORE DRONE TEST CONNECTION !!!
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

    async def fly_route(self, start_addr: str, end_addr: str, cruise_alt=30.0):
        start = await asyncio.to_thread(self.maps.geocode, start_addr); start.alt = cruise_alt
        dest  = await asyncio.to_thread(self.maps.geocode, end_addr); dest.alt = cruise_alt
        self._running = True
        self._flight_id = await self.repo.create_flight(
            start_lat=start.lat, start_lon=start.lon, start_alt=start.alt,
            dest_lat=dest.lat,   dest_lon=dest.lon,   dest_alt=dest.alt,
        )
        await self.repo.add_event(self._flight_id, "mission_created", {"alt": cruise_alt})

        self._dest_coord = dest

        await asyncio.sleep(1.0)

        await self.repo.add_event(self._flight_id, "connected", {})

        # Preflight range check (can hard-fail if you want)
        home = _coord_from_home(self.drone.home_location)

        preflight = await self._preflight_range_check(home, start, dest)
        if not preflight.feasible and settings.ENFORCE_PREFLIGHT_RANGE:
            raise RuntimeError(preflight.reason)

        async def _telemetry_logger():
            while self._running:
                t = self.drone.get_telemetry()
                await self.repo.add_telemetry(
                    self._flight_id,
                    lat=t.lat, lon=t.lon, alt=t.alt,
                    heading=t.heading, groundspeed=t.groundspeed,
                    armed=t.armed, mode=t.mode,
                    battery_voltage=t.battery_voltage,
                    battery_current=t.battery_current,
                    battery_level=t.battery_level,
                )
                await asyncio.sleep(1.0)

        self._telemetry_task = asyncio.create_task(_telemetry_logger())

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
        level_frac = None if t.battery_level is None else max(0.0, min(1.0, float(t.battery_level) / 100.0))

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
        """Re-evaluate remaining distance periodically and warn if we’re going to run short."""
        while self._running:
            try:
                if self._dest_coord:
                    t = self.drone.get_telemetry()
                    remain_km = haversine_km(t.lat, t.lon, self._dest_coord.lat, self._dest_coord.lon)
                    level = None
                    if t.battery_level is not None:
                        level = max(0.0, min(1.0, float(t.battery_level) / 100.0))
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


    async def telemetry_publish_task(self):
        """Continuously publish telemetry while drone is active"""
        # while self._running:

        try:
            # Publish to MQTT
            self.publisher.start()
        except Exception as e:
            print(f"Telemetry publish error: {e}")

        await asyncio.sleep(self._telemetry_interval)

    async def telemetry_task(self):
        while self._running:
            t = self.drone.get_telemetry()
            # Publish to MQTT
            self.mqtt.publish("drone/telemetry", t.__dict__, qos=0)
            # Update OPC UA
            await self.opcua.update_telemetry(t)
            await asyncio.sleep(1.0)

    async def telemetry_logging_task(self):
        # Persist at a slower, configurable cadence
        interval = max(0.5, settings.telem_log_interval_sec)
        while self._running:
            t = self.drone.get_telemetry()
            try:
                await self.repo.save(t)
            except Exception as e:
                # You can add proper logging here
                pass
            await asyncio.sleep(interval)

    async def vision_task(self):
        try:
            for _, frame in self.video.frames():
                dets = await self.analyzer.detect_objects(frame)
                payload = [d.__dict__ for d in dets]
                self.mqtt.publish("drone/detections", payload, qos=0)
                await self.opcua.update_detections(json.dumps(payload))
                await asyncio.sleep(0)  # yield
        except RuntimeError as e:
            self.mqtt.publish("drone/events", {"level":"error","msg":str(e)})


    async def run(self, start_addr: str, end_addr: str, alt=30.0):
        logging.info(f"🚁 Starting safe flight from {start_addr} to {end_addr}")
        # print(f"🚁 Starting safe flight from {start_addr} to {end_addr}")

        await self.opcua.start()
        self.drone.connect()

        # Start all tasks including the critical heartbeat task
        tasks = [
            # asyncio.create_task(self.telemetry_publish_task()),
            asyncio.create_task(self.telemetry_task()),
            asyncio.create_task(self.telemetry_logging_task()),
            # asyncio.create_task(self.vision_task()),
            asyncio.create_task(self._range_guard_task()),
            asyncio.create_task(self.heartbeat_task()),  # CRITICAL SAFETY TASK
            asyncio.create_task(self.emergency_monitor_task()),
        ]

        try:
            # Announce flight start
            # self.mqtt.publish("drone/events", {
            #     "type": "flight_start",
            #     "from": start_addr,
            #     "to": end_addr,
            #     "altitude": alt,
            #     "heartbeat_timeout": self.drone.heartbeat_timeout,
            #     "timestamp": time.time()
            # })

            await self.fly_route(start_addr, end_addr, cruise_alt=alt)

            # If we get here, flight completed successfully
            # self.mqtt.publish("drone/events", {
            #     "type": "flight_completed",
            #     "timestamp": time.time()
            # })

        except Exception as e:
            logging.info(f"❌ Flight error: {e}")
            # print(f"❌ Flight error: {e}")
            # self.mqtt.publish("drone/errors", {
            #     "type": "flight_error",
            #     "message": str(e),
            #     "timestamp": time.time()
            # })
            raise
        finally:
            logging.info("🛑 Shutting down flight operations...")
            # print("🛑 Shutting down flight operations...")
            self._running = False
            await asyncio.sleep(0.5)  # Give tasks time to see the flag

            if getattr(self, "_telemetry_task", None):
                self._telemetry_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._telemetry_task

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
            # self.video.close()
            self.drone.close()

            if self.publisher.is_running:
                # print("Stopping telemetry publisher...")
                logging.info("Stopping telemetry publisher...")
                self.publisher.stop()

            # print("✅ Safe shutdown completed")
            logging.info("✅ Safe shutdown completed")

