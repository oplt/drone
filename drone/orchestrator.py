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
from utils.geo import haversine_km



class Orchestrator:
    def __init__(
            self,
            drone: DroneClient,
            maps: GoogleMapsClient,
            analyzer: LLMAnalyzer,
            mqtt: MqttClient,
            opcua: DroneOpcUaServer,
            video: VideoStream,
            telemetry_repo: TelemetryRepository,
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
        self._heartbeat_task = None

    async def heartbeat_task(self):
        """Send regular heartbeats to keep the dead man's switch happy"""
        print("Starting heartbeat task...")
        while self._running:
            try:
                self.drone.send_heartbeat()
                # Also publish heartbeat status to MQTT for monitoring
                self.mqtt.publish("drone/heartbeat", {
                    "timestamp": time.time(),
                    "status": "alive"
                }, qos=1)  # QoS 1 for important heartbeat messages
                await asyncio.sleep(2.0)  # Send every 2 seconds
            except Exception as e:
                print(f"⚠️  Error in heartbeat task: {e}")
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
                print(f"Error in emergency monitor: {e}")
                await asyncio.sleep(1.0)

    async def fly_route(self, start_addr: str, end_addr: str, cruise_alt=30.0):
        start = self.maps.geocode(start_addr); start.alt = cruise_alt
        dest = self.maps.geocode(end_addr); dest.alt = cruise_alt
        self._dest_coord = dest

        self.drone.connect()

        # Preflight range check (can hard-fail if you want)
        preflight = await self._preflight_range_check(dest)
        if not preflight.feasible:
            # Abort takeoff; still keep services running so user sees the warning
            raise RuntimeError(f"Preflight failed: {preflight.reason}")

        self.drone.arm_and_takeoff(cruise_alt)
        path = list(self.maps.waypoints_between(start, dest, steps=6))
        self.drone.follow_waypoints(path)
        self.drone.land()

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

    async def _preflight_range_check(self, dest: Coordinate) -> RangeEstimateResult:
        # assume drone position from telemetry
        t = self.drone.get_telemetry()
        distance_km = haversine_km(t.lat, t.lon, dest.lat, dest.lon)
        level = None
        # battery_level expected 0-100 (DroneKit) → convert to 0..1
        if t.battery_level is not None:
            level = max(0.0, min(1.0, float(t.battery_level) / 100.0))
        res = self._estimate_range(distance_km, level)
        # Inform MQTT + OPC UA
        self.mqtt.publish("drone/warnings", {
            "type": "preflight_range",
            "distance_km": distance_km,
            "est_range_km": res.est_range_km,
            "feasible": res.feasible,
            "note": res.reason
        })
        await self.opcua.update_range(res.est_range_km or 0.0, res.feasible, res.reason)
        return res

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
                pass
            await asyncio.sleep(2.0)  # evaluation interval

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
        print(f"🚁 Starting safe flight from {start_addr} to {end_addr}")

        await self.opcua.start()

        # Start all tasks including the critical heartbeat task
        tasks = [
            asyncio.create_task(self.telemetry_task()),
            asyncio.create_task(self.telemetry_logging_task()),
            asyncio.create_task(self.vision_task()),
            asyncio.create_task(self._range_guard_task()),
            asyncio.create_task(self.heartbeat_task()),  # CRITICAL SAFETY TASK
            asyncio.create_task(self.emergency_monitor_task()),
        ]

        try:
            # Announce flight start
            self.mqtt.publish("drone/events", {
                "type": "flight_start",
                "from": start_addr,
                "to": end_addr,
                "altitude": alt,
                "heartbeat_timeout": self.drone.heartbeat_timeout,
                "timestamp": time.time()
            })

            await self.fly_route(start_addr, end_addr, cruise_alt=alt)

            # If we get here, flight completed successfully
            self.mqtt.publish("drone/events", {
                "type": "flight_completed",
                "timestamp": time.time()
            })

        except Exception as e:
            print(f"❌ Flight error: {e}")
            self.mqtt.publish("drone/errors", {
                "type": "flight_error",
                "message": str(e),
                "timestamp": time.time()
            })
            raise
        finally:
            print("🛑 Shutting down flight operations...")
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
            self.video.close()
            self.drone.close()

            print("✅ Safe shutdown completed")

