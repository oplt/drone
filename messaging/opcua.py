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
        self.server.set_endpoint(self.endpoint)

        # DEV: only expose an open endpoint (no certs needed, no warnings)
        self.server.set_security_policy([ua.SecurityPolicyType.NoSecurity])


        self.idx = await self.server.register_namespace("drone.vision")
        # self.objects = self.server.nodes.objects
        self.objects = self.server.get_objects_node()
        drone = await self.objects.add_object(self.idx, "Telemetry")
        self.vars["Lat"] = await drone.add_variable(self.idx, "Lat", 0.0)
        self.vars["Lon"] = await drone.add_variable(self.idx, "Lon", 0.0)
        self.vars["Alt"] = await drone.add_variable(self.idx, "Alt", 0.0)
        self.vars["Heading"] = await drone.add_variable(self.idx, "Heading", 0.0)
        self.vars["Groundspeed"] = await drone.add_variable(self.idx, "Groundspeed", 0.0)
        self.vars["Armed"] = await drone.add_variable(self.idx, "Armed", False)
        self.vars["battery_voltage"] = await drone.add_variable(self.idx, "battery_voltage", None)  # Volts
        self.vars["battery_current"] = await drone.add_variable(self.idx, "battery_current",   None)
        self.vars["battery_remaining"] = await drone.add_variable(self.idx, "battery_remaining", None)  # Percent (0-100)

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


    async def stop(self):
        await self.server.stop()
