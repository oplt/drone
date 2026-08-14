from __future__ import annotations

from backend.infrastructure.vehicle.mavlink.commands import MavlinkCommandsMixin
from backend.infrastructure.vehicle.mavlink.connection import MavlinkConnectionMixin
from backend.infrastructure.vehicle.mavlink.heartbeat import MavlinkHeartbeatMixin
from backend.infrastructure.vehicle.mavlink.landing import MavlinkLandingMixin
from backend.infrastructure.vehicle.mavlink.local_control import MavlinkLocalControlMixin
from backend.infrastructure.vehicle.mavlink.navigation import MavlinkNavigationMixin
from backend.infrastructure.vehicle.mavlink.overlay import MavlinkOverlayMixin
from backend.infrastructure.vehicle.mavlink.takeoff import MavlinkTakeoffMixin
from backend.infrastructure.vehicle.mavlink.telemetry import MavlinkTelemetryMixin
from backend.infrastructure.vehicle.mavlink.waypoint_follow import MavlinkWaypointFollowMixin
from backend.modules.vehicle_runtime.vehicle_port import DroneClient


class MavlinkDrone(
    MavlinkConnectionMixin,
    MavlinkOverlayMixin,
    MavlinkHeartbeatMixin,
    MavlinkTakeoffMixin,
    MavlinkNavigationMixin,
    MavlinkTelemetryMixin,
    MavlinkCommandsMixin,
    MavlinkWaypointFollowMixin,
    MavlinkLocalControlMixin,
    MavlinkLandingMixin,
    DroneClient,
):
    """Synchronous MAVLink SDK adapter.

    Methods intentionally remain blocking because DroneKit/PyMAVLink owns its
    polling model. Async services must invoke them through the shared
    ``run_blocking(..., boundary='mavlink')`` adapter.
    """
