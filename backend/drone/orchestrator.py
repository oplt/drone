import asyncio
import time
import logging
from .models import Coordinate
from .drone_base import DroneClient
from backend.map.google_maps import GoogleMapsClient
from backend.video.stream import DroneVideoStream
from backend.analysis.llm import LLMAnalyzer
from backend.messaging.mqtt import MqttClient, MqttPublisher
# from backend.messaging.opcua import DroneOpcUaServer
from backend.db.repository.telemetry_repo import TelemetryRepository
from backend.config import settings
from backend.analysis.range_estimator import SimpleWhPerKmModel, RangeEstimateResult
from backend.utils.geo import haversine_km, coord_from_home
from backend.flight.preflight_check.preflight_orch import PreflightOrchestrator
from backend.flight.preflight_check.schemas import CheckStatus

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(
            self,
            drone: DroneClient,
            maps: GoogleMapsClient,
            analyzer: LLMAnalyzer,
            mqtt: MqttClient | None,
            # opcua: DroneOpcUaServer,
            video: DroneVideoStream | None,
            telemetry_repo: TelemetryRepository,
            publisher: MqttPublisher | None,
    ):
        self.drone = drone
        self.maps = maps
        self.analyzer = analyzer
        self.mqtt = mqtt
        # self.opcua = opcua
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
                if self.mqtt:
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
            if not self.publisher:
                return
            if not await asyncio.to_thread(self.publisher.start):
                logger.error("Failed to start telemetry publisher")
                return

            # Just keep this task alive while publisher runs
            while self._running and self.publisher.is_alive():
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Telemetry publisher error: {e}")
        finally:
            if self.publisher and self.publisher.is_running:
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
                    if self.mqtt:
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
                    # await self.opcua.update_video_status(
                    #     healthy=status["healthy"],
                    #     fps=status["fps"],
                    #     recording=status["recording"],
                    # )

                    # Log warnings if video is unhealthy
                    if not status["healthy"]:
                        logging.warning("Video stream is unhealthy")
                        if self.mqtt:
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

    async def mqtt_subscriber_task(self):
        try:
            while self._flight_id is None:
                logger.info(
                    "Waiting for flight_id to be set before starting MQTT subscriber..."
                )
                await asyncio.sleep(0.5)

            logger.info(f"Starting MQTT subscriber with flight_id: {self._flight_id}")

            if not self.mqtt:
                return

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
                # Only act if the drone explicitly flagged an emergency trigger.
                if getattr(self.drone, "dead_mans_switch_triggered", False):
                    if self.mqtt:
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
                    # Reset to avoid repeated notifications
                    try:
                        self.drone.dead_mans_switch_triggered = False
                    except Exception:
                        pass
                    break
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.info(f"Error in emergency monitor: {e}")
                await asyncio.sleep(1.0)


    async def _run_preflight_checks(
            self,
            waypoints: list[Coordinate],
            alt: float,
            **kwargs,
    ):

        mission_data = {
            "type": "route",
            "waypoints": [
                {"lat": w.lat, "lon": w.lon, "alt": getattr(w, "alt", None) or alt}
                for w in waypoints
            ],
            "speed": kwargs.pop("mission_speed", settings.cruise_speed_mps),
            "altitude_agl": alt,
        }

        vehicle_state = await asyncio.to_thread(self.drone.get_telemetry)
        orchestrator = PreflightOrchestrator(config=kwargs.pop("preflight_config", {}))
        config_overrides = dict(kwargs.pop("config_overrides", {}) or {})
        runtime_preflight = {
            "ENFORCE_PREFLIGHT_RANGE": settings.enforce_preflight_range,
            "HDOP_MAX": settings.HDOP_MAX,
            "SAT_MIN": settings.SAT_MIN,
            "HOME_MAX_DIST": settings.HOME_MAX_DIST,
            "GPS_FIX_TYPE_MIN": settings.GPS_FIX_TYPE_MIN,
            "EKF_THRESHOLD": settings.EKF_THRESHOLD,
            "COMPASS_HEALTH_REQUIRED": settings.COMPASS_HEALTH_REQUIRED,
            "BATTERY_MIN_V": settings.BATTERY_MIN_V,
            "BATTERY_MIN_PERCENT": settings.BATTERY_MIN_PERCENT,
            # Legacy aliases still used by some checks.
            "BATTERY_RESERVE_PCT": settings.BATTERY_MIN_PERCENT,
            "HEARTBEAT_MAX_AGE": settings.HEARTBEAT_MAX_AGE,
            "MSG_RATE_MIN_HZ": settings.MSG_RATE_MIN_HZ,
            "RTL_MIN_ALT": settings.RTL_MIN_ALT,
            "MIN_CLEARANCE": settings.MIN_CLEARANCE,
            "MIN_CLEARANCE_M": settings.MIN_CLEARANCE,
            "AGL_MIN": settings.AGL_MIN,
            "AGL_MAX": settings.AGL_MAX,
            "MAX_RANGE_M": settings.MAX_RANGE_M,
            "MAX_WAYPOINTS": settings.MAX_WAYPOINTS,
            "NFZ_BUFFER_M": settings.NFZ_BUFFER_M,
            "A_LAT_MAX": settings.A_LAT_MAX,
            "BANK_MAX_DEG": settings.BANK_MAX_DEG,
            "TURN_PENALTY_S": settings.TURN_PENALTY_S,
            "WP_RADIUS_M": settings.WP_RADIUS_M,
        }
        for key, value in runtime_preflight.items():
            config_overrides.setdefault(key, value)

        report = await orchestrator.run(
            vehicle_state,
            mission_data,
            flight_id=str(self._flight_id),
            allowed_modes=["STANDBY", "GUIDED", "AUTO", "LOITER"],
            config_overrides=config_overrides,
            **kwargs,
        )

        # --- log every individual result ---
        logger.info(
            f"Preflight overall: {report.overall_status} | "
            f"pass={report.summary.get('passed', 0)} "
            f"warn={report.summary.get('warned', 0)} "
            f"fail={report.summary.get('failed', 0)}"
        )
        for result in report.base_checks + report.mission_checks:
            level = (
                logging.WARNING if result.status == CheckStatus.WARN
                else logging.ERROR if result.status == CheckStatus.FAIL
                else logging.DEBUG
            )
            logger.log(level, f"  [{result.status}] {result.name}: {result.message or ''}")

        # --- publish report to MQTT so the ground station sees it ---
        if self.mqtt:
            self.mqtt.publish(
                "drone/preflight",
                {
                    "timestamp": time.time(),
                    "overall": report.overall_status,
                    "summary": report.summary,
                    "critical_failures": (
                        [{"name": c.name, "message": c.message}
                         for c in report.critical_failures]
                        if report.critical_failures else []
                    ),
                },
                qos=1,
            )

        # --- persist to DB ---
        if self._flight_id is not None:
            await self.repo.add_event(
                self._flight_id,
                "preflight_report",
                {
                    "overall": report.overall_status,
                    "summary": report.summary,
                    "critical_failures": (
                        [c.name for c in report.critical_failures]
                        if report.critical_failures else []
                    ),
                },
            )

        # --- abort on hard failure ---
        if report.overall_status == CheckStatus.FAIL:
            failed_names = (
                [c.name for c in report.critical_failures]
                if report.critical_failures
                else [r.name for r in report.base_checks + report.mission_checks
                      if r.status == CheckStatus.FAIL]
            )
            raise RuntimeError(
                f"Preflight FAILED - mission aborted. "
                f"Failed checks: {', '.join(failed_names)}"
            )

        # WARN is non-fatal: mission continues but operator has been notified
        if report.overall_status == CheckStatus.WARN:
            logger.warning("Preflight passed with warnings - proceeding with caution")

        return report


    async def run_mission(self, mission: "Mission", alt: float = 30.0, flight_fn=None):

        self._flight_id = None
        self._running = True
        tasks: list[asyncio.Task] = []
        waypoints = mission.get_waypoints()
        cruise_alt = alt

        # ------------------------------------------------------------------
        # STEP 1: Connect to drone
        # ------------------------------------------------------------------
        try:
            logger.info("🔌 Connecting to drone...")
            await asyncio.to_thread(self.drone.connect)
            logger.info("✅ Drone connected successfully")
        except Exception as e:  # FIX (Bug 2): bare except → except Exception as e
            logger.exception(f"❌ Drone Connection failed: {e}")
            raise

        # ------------------------------------------------------------------
        # STEP 2: Create flight record
        # ------------------------------------------------------------------
        try:
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
            await self.repo.add_event(
                self._flight_id,
                "mission_created",
                {"alt": cruise_alt, "waypoints": len(waypoints)},
            )
            await self.repo.add_event(self._flight_id, "connected", {})
            logger.info(f"✅ Created flight record with ID: {self._flight_id}")
        except Exception as e:  # FIX (Bug 2)
            logger.exception(f"❌ Flight record generation failed: {e}")
            raise

        # ------------------------------------------------------------------
        # STEP 3: Preflight checks
        # ------------------------------------------------------------------
        try:
            logger.info("🔍 Running preflight checks...")
            await self._run_preflight_checks(waypoints, alt)
            logger.info("✅ Preflight checks passed")
        except Exception as e:  # FIX (Bug 2)
            logger.exception(f"❌ Preflight checks failed: {e}")
            raise

        # ------------------------------------------------------------------
        # STEP 4: Start telemetry stream
        # ------------------------------------------------------------------
        try:
            from backend.config import settings
            from backend.messaging.websocket import telemetry_manager

            if not telemetry_manager._running:
                logger.info("Starting telemetry stream...")
                await asyncio.to_thread(
                    telemetry_manager.start_telemetry_stream,
                    settings.drone_conn_mavproxy
                )
                logger.info("✅ Telemetry stream started")
                await asyncio.sleep(1)
        except Exception as e:  # FIX (Bug 2)
            logger.warning(f"⚠️ Failed to start telemetry stream: {e}")
            raise

        # ------------------------------------------------------------------
        # STEP 5: Start background tasks, run flight, then clean up.
        # ------------------------------------------------------------------
        try:
            tasks = [
                asyncio.create_task(self.heartbeat_task()),
                asyncio.create_task(self.telemetry_publish_task()),
                asyncio.create_task(self.mqtt_subscriber_task()),
                asyncio.create_task(self._raw_event_ingest_worker()),
                asyncio.create_task(self.video_health_monitor_task()),
                asyncio.create_task(self.emergency_monitor_task()),
            ]
            if flight_fn is not None:
                await flight_fn()

        except Exception as e:
            logger.exception(f"❌ Mission failed: {e}")
            raise
        finally:
            # Graceful teardown — always runs after flight completes or fails.
            self._running = False

            for task in tasks:
                if task and not task.done():
                    task.cancel()

            if tasks:
                await asyncio.gather(
                    *[t for t in tasks if not t.done()],
                    return_exceptions=True,
                )

            await self._cleanup()


    async def _cleanup(self):
        """Clean up orchestrator resources"""
        try:
            self.drone.stop_dead_mans_switch()
        except Exception as e:
            logger.warning(f"Failed to stop dead man's switch: {e}")

        # if self.opcua:
        #     try:
        #         await self.opcua.stop()
        #     except Exception as e:
        #         logger.warning(f"Failed to stop OPC UA server: {e}")

        if self.video:
            try:
                self.video.close()
            except Exception as e:
                logger.warning(f"Failed to close video stream: {e}")

        try:
            self.drone.close()
        except Exception as e:
            logger.warning(f"Failed to close drone connection: {e}")

        if self.publisher and getattr(self.publisher, "is_running", False):
            try:
                self.publisher.stop()
            except Exception as e:
                logger.warning(f"Failed to stop telemetry publisher: {e}")