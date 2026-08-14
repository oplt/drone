import collections.abc
import time

for _name in ("MutableMapping", "MutableSequence", "MutableSet"):
    if not hasattr(collections, _name):
        setattr(collections, _name, getattr(collections.abc, _name))

from dronekit import connect

from backend.infrastructure.vehicle.mavlink import MavlinkDrone, WaypointFollowerConfig
from backend.observability.instruments import observed_span

__all__ = [
    "MavlinkDrone",
    "WaypointFollowerConfig",
    "connect",
    "observed_span",
    "time",
]
