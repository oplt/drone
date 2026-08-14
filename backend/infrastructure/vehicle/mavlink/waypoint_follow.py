from __future__ import annotations

import logging

from backend.infrastructure.vehicle.mavlink._client_refs import client_module
from backend.infrastructure.vehicle.mavlink.config import WaypointFollowerConfig, logger
from backend.modules.vehicle_runtime.types import Coordinate
from backend.modules.vehicle_runtime.vehicle_port import MissionAbortRequested


class MavlinkWaypointFollowMixin:
    """Segment-based waypoint follower."""

    def follow_waypoints(self, path) -> None:
        """
        Fly the drone through every Coordinate in *path* using the
        segment-based follower.  Tune behaviour by setting
        ``self.follower_config`` before calling.
        """
        self._mission_abort_requested.clear()
        self._mission_pause_requested.clear()
        self._fly_segment_path(list(path), self.follower_config)

    def _fly_segment_path(
        self,
        path: list[Coordinate],
        config: WaypointFollowerConfig,
    ) -> None:
        """
        Segment-based inner loop for follow_waypoints.

        For each waypoint i:
          1. Issue goto(path[i]).
          2. Poll every config.poll_interval_s.
          3. When distance < config.lookahead_m and the next waypoint exists,
             issue goto(path[i+1]) once (turn anticipation — vehicle begins
             curving before reaching the acceptance sphere).
          4. When distance < config.acceptance_radius_m advance to i+1.
          5. Track paused time so the per-leg timeout counts only active
             flight time.
          6. Raise MissionAbortRequested on operator abort.
          7. Raise RuntimeError when a leg exceeds config.max_active_leg_s.
        """
        n = len(path)
        if n == 0:
            return

        cfg = config
        lookahead_m = max(0.0, cfg.lookahead_m)

        for i, target in enumerate(path):
            self.goto(target)
            logger.debug("Segment follower: heading to wp %d/%d %s", i + 1, n, target)

            start_time = client_module().time.monotonic()
            paused_started_at: float | None = None
            paused_total_s = 0.0
            was_paused = False
            lookahead_issued = False  # guard: only issue next-wp command once per leg

            while True:
                if self._mission_abort_requested.is_set():
                    raise MissionAbortRequested("Operator abort requested")

                if self._mission_pause_requested.is_set():
                    if paused_started_at is None:
                        paused_started_at = client_module().time.monotonic()
                        was_paused = True
                    self._mission_control_changed.wait(timeout=cfg.poll_interval_s)
                    self._mission_control_changed.clear()
                    continue

                # Accumulate paused time after unpausing.
                if paused_started_at is not None:
                    paused_total_s += client_module().time.monotonic() - paused_started_at
                    paused_started_at = None
                if was_paused:
                    # Re-issue current target so autopilot resumes toward it.
                    self.goto(target)
                    lookahead_issued = False  # reset — drone may have drifted
                    was_paused = False

                current = self.vehicle.location.global_relative_frame
                dist = self._distance_to_target(current, target)

                if cfg.on_progress is not None:
                    try:
                        cfg.on_progress(i, n, dist)
                    except Exception:
                        logger.exception("WaypointFollowerConfig.on_progress raised")

                # Lookahead: begin commanding the next waypoint early so the
                # autopilot can start curving into the turn before reaching
                # the acceptance sphere.
                if not lookahead_issued and lookahead_m > 0 and dist < lookahead_m and i + 1 < n:
                    self.goto(path[i + 1])
                    lookahead_issued = True
                    logger.debug(
                        "Segment follower: lookahead fired at %.1f m — pre-commanding wp %d/%d",
                        dist,
                        i + 2,
                        n,
                    )

                if dist < cfg.acceptance_radius_m:
                    logger.debug("Segment follower: wp %d/%d accepted at %.1f m", i + 1, n, dist)
                    break

                active_elapsed_s = (client_module().time.monotonic() - start_time) - paused_total_s
                if active_elapsed_s > cfg.max_active_leg_s:
                    raise RuntimeError(
                        f"Waypoint leg {i + 1}/{n} timed out after "
                        f"{cfg.max_active_leg_s:.0f}s active flight time "
                        f"(dist={dist:.1f}m)"
                    )

                self._mission_control_changed.wait(timeout=cfg.poll_interval_s)
                self._mission_control_changed.clear()

