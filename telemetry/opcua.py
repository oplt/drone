import asyncio
from asyncua import ua, Server
from config import settings

class DroneOpcUaServer:
    def __init__(self):
        self.endpoint = settings.opcua_endpoint
        self.server = Server()
        self.idx = None
        self.objects = None
        self.vars = {}

    async def start(self):
        await self.server.init()
        # self.server.set_endpoint(self.endpoint)

        # DEV: only expose an open endpoint (no certs needed, no warnings)
        self.server.set_security_policy([ua.SecurityPolicyType.NoSecurity])


        self.idx = await self.server.register_namespace("drone.vision")
        # self.objects = self.server.nodes.objects
        self.objects = self.server.get_objects_node()
        drone = await self.objects.add_object(self.idx, "Telemetry")
        self.vars["lat"] = await drone.add_variable(self.idx, "Lat", 0.0)
        self.vars["lon"] = await drone.add_variable(self.idx, "Lon", 0.0)
        self.vars["alt"] = await drone.add_variable(self.idx, "Alt", 0.0)
        self.vars["heading"] = await drone.add_variable(self.idx, "Heading", 0.0)
        self.vars["groundspeed"] = await drone.add_variable(self.idx, "Groundspeed", 0.0)
        # self.vars["Armed"] = await drone.add_variable(self.idx, "Armed", False)
        # Initialize with concrete types to avoid VariantType.Null mismatches
        self.vars["battery_voltage"] = await drone.add_variable(self.idx, "battery_voltage", 0.0)  # Volts (Double)
        self.vars["battery_current"] = await drone.add_variable(self.idx, "battery_current", 0.0)  # Amps (Double)
        self.vars["battery_remaining"] = await drone.add_variable(self.idx, "battery_remaining", -1)  # Percent (Int)
        self.vars["mode"] = await drone.add_variable(self.idx, "Mode", "UNKNOWN")
        self.vars["system_time"] = await drone.add_variable(self.idx, "system_time", 0.0)  # UTC timestamp (Double seconds)


        for v in self.vars.values():
            await v.set_writable()  # allow updates
        await self.server.start()


    # async def update_telemetry(self, t):
    #     await self.vars["Lat"].write_value(t.lat)
    #     await self.vars["Lon"].write_value(t.lon)
    #     await self.vars["Alt"].write_value(t.alt)
    #     await self.vars["Heading"].write_value(float(t.heading))
    #     await self.vars["Groundspeed"].write_value(float(t.groundspeed))
    #     await self.vars["Armed"].write_value(bool(t.armed))
    #     await self.vars["Mode"].write_value(str(t.mode))


    async def update_detections(self, detections_json: str):
        """Update OPC UA with detection data"""
        try:
            import json
            detections = json.loads(detections_json) if isinstance(detections_json, str) else detections_json
            
            # Add detection count variable if it doesn't exist
            if "detection_count" not in self.vars:
                detection_obj = await self.objects.add_object(self.idx, "Detections")
                self.vars["detection_count"] = await detection_obj.add_variable(self.idx, "Count", 0)
                await self.vars["detection_count"].set_writable()
            
            # Update detection count
            count = len(detections) if isinstance(detections, list) else 0
            await self.vars["detection_count"].write_value(count)
            
        except Exception as e:
            # Log but don't fail - OPC UA updates are not critical
            import logging
            logging.debug(f"Failed to update OPC UA detections: {e}")

    async def update_video_status(self, healthy: bool, fps: float, recording: bool):
        """Update OPC UA with video status"""
        try:
            # Add video status variables if they don't exist
            if "video_healthy" not in self.vars:
                video_obj = await self.objects.add_object(self.idx, "Video")
                self.vars["video_healthy"] = await video_obj.add_variable(self.idx, "Healthy", False)
                self.vars["video_fps"] = await video_obj.add_variable(self.idx, "FPS", 0.0)
                self.vars["video_recording"] = await video_obj.add_variable(self.idx, "Recording", False)
                for v in ["video_healthy", "video_fps", "video_recording"]:
                    await self.vars[v].set_writable()
            
            await self.vars["video_healthy"].write_value(healthy)
            await self.vars["video_fps"].write_value(fps)
            await self.vars["video_recording"].write_value(recording)
            
        except Exception as e:
            import logging
            logging.debug(f"Failed to update OPC UA video status: {e}")

    async def update_range(self, est_range_km: float, feasible: bool, reason: str):
        """Update OPC UA with range estimation"""
        try:
            # Add range variables if they don't exist
            if "range_km" not in self.vars:
                range_obj = await self.objects.add_object(self.idx, "Range")
                self.vars["range_km"] = await range_obj.add_variable(self.idx, "EstimatedRangeKm", 0.0)
                self.vars["range_feasible"] = await range_obj.add_variable(self.idx, "Feasible", False)
                for v in ["range_km", "range_feasible"]:
                    await self.vars[v].set_writable()
            
            await self.vars["range_km"].write_value(est_range_km)
            await self.vars["range_feasible"].write_value(feasible)
            
        except Exception as e:
            import logging
            logging.debug(f"Failed to update OPC UA range: {e}")

    async def stop(self):
        """Stop OPC UA server safely"""
        try:
            if self.server and hasattr(self.server, 'stop'):
                await self.server.stop()
        except Exception as e:
            import logging
            logging.debug(f"Error stopping OPC UA server: {e}")
