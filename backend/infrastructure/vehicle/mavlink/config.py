from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from pymavlink import mavutil

from backend.modules.missions.flight_profile import explicit_sim_home_fallback_enabled

logger = logging.getLogger(__name__)


@dataclass
class WaypointFollowerConfig:
    """
    Tuning parameters for the segment-based waypoint follower.

    acceptance_radius_m
        Distance to the *current* target waypoint at which the follower
        considers that waypoint reached and advances to the next one.
        Default 3.0 m suits GPS-class outdoor surveys; tighten for dense
        grid legs or loosen for fast transit legs.

    lookahead_m
        Distance to the current target at which the follower issues the
        *next* waypoint command early.  This lets the autopilot begin
        curving toward the turn before reaching the waypoint, reducing
        braking and improving survey coverage on dense grid missions.
        Must be >= acceptance_radius_m; if set to 0 lookahead is disabled.

    poll_interval_s
        How often (seconds) the position is checked inside the control
        loop.  0.2 s gives a tighter reaction than the original 1 s loop.

    max_active_leg_s
        Wall-clock limit per waypoint leg (paused time not counted).
        Raises RuntimeError when exceeded.

    on_progress
        Optional callback invoked each poll cycle:
        ``on_progress(wp_index, total_waypoints, distance_m) -> None``.
        Runs in the thread executing follow_waypoints; must not block.
    """

    acceptance_radius_m: float = 3.0
    lookahead_m: float = 5.0
    poll_interval_s: float = 0.2
    max_active_leg_s: float = 300.0
    on_progress: Callable[[int, int, float], None] | None = field(default=None, repr=False)


logger = logging.getLogger(__name__)


def _sim_or_indoor_home_fallback_allowed() -> bool:
    return explicit_sim_home_fallback_enabled()


def _mavlink_command_name(command: int) -> str:
    enum = getattr(getattr(mavutil, "mavlink", None), "enums", {}).get("MAV_CMD", {})
    entry = enum.get(int(command)) if isinstance(enum, dict) else None
    return str(getattr(entry, "name", None) or command)


