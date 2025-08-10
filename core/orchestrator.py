import asyncio, json, time
from typing import Iterable
from core.models import Coordinate
from core.drone_base import DroneClient
from core.google_maps import GoogleMapsClient
from core.stream import VideoStream
from core.llm import LLMAnalyzer
from messaging.mqtt import MqttClient
from messaging.opcua import DroneOpcUaServer

class Orchestrator:
    def __init__(
            self,
            drone: DroneClient,
            maps: GoogleMapsClient,
            analyzer: LLMAnalyzer,
            mqtt: MqttClient,
            opcua: DroneOpcUaServer,
            video: VideoStream
    ):
        self.drone = drone
        self.maps = maps
        self.analyzer = analyzer
        self.mqtt = mqtt
        self.opcua = opcua
        self.video = video
        self._running = True

    async def fly_route(self, start_addr: str, end_addr: str, cruise_alt=30.0):
        start = self.maps.geocode(start_addr); start.alt = cruise_alt
        end = self.maps.geocode(end_addr); end.alt = cruise_alt
        path = list(self.maps.waypoints_between(start, end, steps=6))

        self.drone.connect()
        self.drone.arm_and_takeoff(cruise_alt)
        self.drone.follow_waypoints(path)
        # land at destination
        self.drone.land()

    async def telemetry_task(self):
        while self._running:
            t = self.drone.get_telemetry()
            # MQTT
            self.mqtt.publish("drone/telemetry", t.__dict__, qos=0)
            # OPC UA
            await self.opcua.update_telemetry(t)
            await asyncio.sleep(1.0)

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
        await self.opcua.start()
        telem = asyncio.create_task(self.telemetry_task())
        vision = asyncio.create_task(self.vision_task())
        try:
            await self.fly_route(start_addr, end_addr, cruise_alt=alt)
        finally:
            self._running = False
            await asyncio.sleep(0.1)
            telem.cancel(); vision.cancel()
            await self.opcua.stop()
            self.video.close()
            self.drone.close()
