from dronekit import connect, VehicleMode, LocationGlobalRelative
from core.models import Coordinate, Telemetry
from core.drone_base import DroneClient
import time

class MavlinkDrone(DroneClient):
    def __init__(self, connection_str: str):
        self.connection_str = connection_str
        self.vehicle = None

    def connect(self) -> None:
        self.vehicle = connect(self.connection_str, wait_ready=True)

    def arm_and_takeoff(self, alt: float) -> None:
        while not self.vehicle.is_armable: time.sleep(1)
        self.vehicle.mode = VehicleMode("GUIDED")
        self.vehicle.armed = True
        while not self.vehicle.armed: time.sleep(1)
        self.vehicle.simple_takeoff(alt)
        while True:
            a = self.vehicle.location.global_relative_frame.alt
            if a >= alt * 0.95: break
            time.sleep(1)

    def goto(self, coord: Coordinate) -> None:
        target = LocationGlobalRelative(coord.lat, coord.lon, coord.alt)
        self.vehicle.simple_goto(target)

    def set_mode(self, mode: str) -> None:
        self.vehicle.mode = VehicleMode(mode)

    def get_telemetry(self) -> Telemetry:
        v = self.vehicle
        loc = v.location.global_relative_frame
        return Telemetry(
            lat=loc.lat, lon=loc.lon, alt=loc.alt,
            heading=v.heading, groundspeed=v.groundspeed,
            armed=v.armed, mode=v.mode.name
        )

    def follow_waypoints(self, path):
        for wp in path:
            self.goto(wp)
            time.sleep(3)  # naive wait; in practice: check distance-to-target

    def land(self) -> None:
        self.vehicle.mode = VehicleMode("LAND")

    def close(self) -> None:
        if self.vehicle: self.vehicle.close()
