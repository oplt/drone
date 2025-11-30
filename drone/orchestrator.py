# drone/orchestrator.py

from __future__ import annotations

import asyncio
import logging
import time

from .models import Coordinate
from .drone_base import DroneClient
from .flight_manager import FlightManager
from messaging.telemetry_manager import TelemetryManager

from map.google_maps import GoogleMapsClient
from video.stream import RaspberryClient
from analysis.llm import LLMAnalyzer
from analysis.video_pipeline import VideoAnalysisManager

from messaging.mqtt import MqttClient
from messaging.opcua import DroneOpcUaServer
from db.repository import TelemetryRepository
from config import settings, VideoAnalysisConfig
from utils.telemetry_publisher_sim import ArduPilotTelemetryPublisher


class Orchestrator:
    """
    High-level coordinator:
      - resolves addresses -> coordinates
      - creates Flight row
      - starts/stops background tasks
      - delegates to FlightManager / TelemetryManager / VideoAnalysisManager
    """

    def __init__(
            self,
            drone: DroneClient,
            maps: GoogleMapsClient,
            analyzer: LLMAnalyzer,
            mqtt: MqttClient,
            opcua: DroneOpcUaServer,
            video: RaspberryClient | None,
            telemetry_repo: TelemetryRepository,
            publisher: ArduPilotTelemetryPublisher,
            video_cfg: VideoAnalysisConfig | None = None,
    ):
        self.drone = drone
        self.maps = maps
        self.analyzer = analyzer
        self.mqtt = mqtt
        self.opcua = opcua
        self.video = video
        self.repo = telemetry_repo
        self.publisher = publisher

        self._running: bool = True
        self._flight_id: int | None = None

        # Managers (separation of concerns)
        self.flight = FlightManager(
            drone=self.drone,
            maps=self.maps,
            repo=self.repo,
            opcua=self.opcua,
            mqtt=self.mqtt,
        )
        self.telemetry_mgr = TelemetryManager(
            mqtt=self.mqtt,
            publisher=self.publisher,
            repo=self.repo,
        )
        self.video_mgr = VideoAnalysisManager(
            video=self.video,
            analyzer=self.analyzer,
            repo=self.repo,
            mqtt=self.mqtt,
            opcua=self.opcua,
            cfg=video_cfg or VideoAnalysisConfig(),
        )

    # -------------------------------------------------------------------------

    async def heartbeat_task(self) -> None:
        """Send regular heartbeats to keep the dead man's switch happy."""
        logging.info("Starting heartbeat task...")

        while self._running:
            try:
                self.mqtt.publish(
                    "drone/heartbeat",
                    {
                        "timestamp": time.time(),
                        "status": "alive",
                    },
                    qos=1,
                )
                await asyncio.sleep(2.0)
            except Exception as e:
                logging.info(f"⚠️  Error in heartbeat task: {e}")
                self.mqtt.publish(
                    "drone/errors",
                    {
                        "type": "heartbeat_error",
                        "message": str(e),
                        "timestamp": time.time(),
                    },
                )
                await asyncio.sleep(1.0)

    # -------------------------------------------------------------------------

    async def run(self, start_addr: str, end_addr: str, alt: float = 30.0) -> None:
        """
        Main entrypoint used by main.py.
        """
        logging.info(f"🚁 Starting safe flight from {start_addr} to {end_addr}")

        # 1) Resolve addresses -> coordinates
        start: Coordinate = await asyncio.to_thread(
            self.maps.geocode,
            start_addr,
        )
        start.alt = alt

        dest: Coordinate = await asyncio.to_thread(
            self.maps.geocode,
            end_addr,
        )
        dest.alt = alt

        # 2) Create Flight record early (so telemetry / video can attach to it)
        self._flight_id = await self.repo.create_flight(
            start_lat=start.lat,
            start_lon=start.lon,
            start_alt=start.alt,
            dest_lat=dest.lat,
            dest_lon=dest.lon,
            dest_alt=dest.alt,
        )

        # Tell managers about the flight
        self.flight.set_flight_context(self._flight_id, dest)
        self.telemetry_mgr.set_flight_id(self._flight_id)
        self.video_mgr.set_flight_id(self._flight_id)

        # 3) Start OPC UA + connect drone
        await self.opcua.start()
        await asyncio.to_thread(self.drone.connect)

        # 4) Start background tasks
        tasks: list[asyncio.Task] = [
            asyncio.create_task(self.heartbeat_task(), name="heartbeat"),
            asyncio.create_task(self.telemetry_mgr.telemetry_publish_task(), name="telem_publish",),
            asyncio.create_task(self.telemetry_mgr.mqtt_subscriber_task(), name="mqtt_subscriber",),
            asyncio.create_task(self.telemetry_mgr._raw_event_ingest_worker(), name="raw_ingest",),
            asyncio.create_task(self.flight.range_guard_task(), name="range_guard",       ),
            asyncio.create_task(self.flight.emergency_monitor_task(), name="emergency_monitor",),
        ]

        # Video tasks only if video client exists
        if self.video:
            await asyncio.to_thread(self.video.start)
            tasks.append(
                asyncio.create_task(
                    self.video_mgr.video_health_monitor_task(),
                    name="video_health",
                )
            )
            tasks.append(
                asyncio.create_task(
                    self.video_mgr.vision_task(),
                    name="vision",
                )
            )

        try:
            logging.info("Background tasks started, beginning flight...")
            await self.flight.fly_route(start, dest, cruise_alt=alt)

        except Exception as e:
            logging.info(f"❌ Flight error: {e}")
            raise
        finally:
            logging.info("🛑 Shutting down flight operations...")
            self._running = False
            self.flight.stop()
            self.telemetry_mgr.stop()
            self.video_mgr.stop()

            await asyncio.sleep(0.5)

            # Cancel background tasks
            for task in tasks:
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            # Safely stop dead man's switch & close connections
            self.drone.stop_dead_mans_switch()

            await self.opcua.stop()
            if self.video:
                self.video.close()
            self.drone.close()

            if self.publisher.is_running:
                logging.info("Stopping telemetry publisher...")
                self.publisher.stop()

            logging.info("✅ Safe shutdown completed")
