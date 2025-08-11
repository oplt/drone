import asyncio
from asyncua import ua, Server

class DroneOpcUaServer:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.server = Server()
        self.idx = None
        self.objects = None
        self.vars = {}

    async def start(self):
        await self.server.init()
        self.server.set_endpoint(self.endpoint)

        # DEV: only expose an open endpoint (no certs needed, no warnings)
        self.server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        self.server.set_security_IDs(["Anonymous"])  # no username/password

        self.idx = await self.server.register_namespace("drone.vision")
        self.objects = self.server.nodes.objects
        drone = await self.objects.add_object(self.idx, "Drone")
        self.vars["Lat"] = await drone.add_variable(self.idx, "Lat", 0.0)
        self.vars["Lon"] = await drone.add_variable(self.idx, "Lon", 0.0)
        self.vars["Alt"] = await drone.add_variable(self.idx, "Alt", 0.0)
        self.vars["Heading"] = await drone.add_variable(self.idx, "Heading", 0.0)
        self.vars["Groundspeed"] = await drone.add_variable(self.idx, "Groundspeed", 0.0)
        self.vars["Armed"] = await drone.add_variable(self.idx, "Armed", False)
        self.vars["Mode"] = await drone.add_variable(self.idx, "Mode", "UNKNOWN")
        self.vars["LastDetections"] = await drone.add_variable(self.idx, "LastDetections", "[]")
        self.vars["EstRangeKm"] = await drone.add_variable(self.idx, "EstRangeKm", 0.0)
        self.vars["RangeOK"] = await drone.add_variable(self.idx, "RangeOK", False)
        self.vars["RangeNote"] = await drone.add_variable(self.idx, "RangeNote", "")
        for v in ("EstRangeKm","RangeOK","RangeNote"):
            await self.vars[v].set_writable()
        for v in self.vars.values():
            await v.set_writable()  # allow updates
        await self.server.start()

    async def update_telemetry(self, t):
        await self.vars["Lat"].write_value(t.lat)
        await self.vars["Lon"].write_value(t.lon)
        await self.vars["Alt"].write_value(t.alt)
        await self.vars["Heading"].write_value(float(t.heading))
        await self.vars["Groundspeed"].write_value(float(t.groundspeed))
        await self.vars["Armed"].write_value(bool(t.armed))
        await self.vars["Mode"].write_value(str(t.mode))

    async def update_detections(self, det_json: str):
        await self.vars["LastDetections"].write_value(det_json)

    async def update_range(self, est_range_km: float, ok: bool, note: str):
        await self.vars["EstRangeKm"].write_value(float(est_range_km))
        await self.vars["RangeOK"].write_value(bool(ok))
        await self.vars["RangeNote"].write_value(str(note))

    async def stop(self):
        await self.server.stop()
