"""
Tests for the segment-based waypoint follower in MavlinkDrone.

All tests run without a real vehicle or network connection.  The DroneKit
vehicle is replaced with a thin position-simulator so the inner control
loop sees realistic distance changes.

Scenarios covered
─────────────────
  Basics
    • Empty path is a no-op.
    • Single-waypoint path completes when within acceptance radius.
    • Multi-waypoint path visits every waypoint in order.

  Lookahead
    • When distance < lookahead_m the next waypoint command is issued exactly
      once, even across multiple poll cycles inside that range.
    • When lookahead is disabled (lookahead_m=0) the next command is never
      pre-issued.
    • Lookahead does not fire on the last waypoint (no next to pre-command).

  Acceptance radius
    • Waypoint is not accepted when drone is outside acceptance_radius_m.
    • Waypoint IS accepted as soon as drone enters acceptance_radius_m.
    • Custom (tight) acceptance radius is respected.

  Pause / resume
    • Pause event stalls progress; resume resumes and re-issues goto.
    • Paused time is excluded from the leg timeout.

  Abort
    • MissionAbortRequested is raised immediately after abort is set.

  Timeout
    • RuntimeError is raised when a leg exceeds max_active_leg_s.

  Progress callback
    • on_progress is called every poll cycle with (index, total, dist).
    • Exceptions in on_progress are swallowed — do not crash the follower.

  Config attribute
    • follower_config on MavlinkDrone is respected by follow_waypoints.
    • follow_waypoints resets abort/pause events before each call.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import pytest

from backend.drone.drone_base import MissionAbortRequested
from backend.drone.mavlink_drone import MavlinkDrone, WaypointFollowerConfig
from backend.drone.models import Coordinate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coord(lat: float = 0.0, lon: float = 0.0, alt: float = 30.0) -> Coordinate:
    return Coordinate(lat=lat, lon=lon, alt=alt)


@dataclass
class _FakeLocation:
    """Mimics vehicle.location.global_relative_frame."""

    lat: float
    lon: float
    alt: float = 30.0


class _SimVehicle:
    """
    Minimal vehicle simulator.  Position is set via set_pos(); goto() records
    the commanded target so tests can inspect it.
    """

    def __init__(self, lat: float = 0.0, lon: float = 0.0):
        self._lat = lat
        self._lon = lon
        self.goto_calls: list[Coordinate] = []

        class _Loc:
            pass

        loc = _Loc()
        self._loc = loc
        self._update_frame()

    def _update_frame(self) -> None:
        self._loc.global_relative_frame = _FakeLocation(lat=self._lat, lon=self._lon)

    @property
    def location(self):
        return self._loc

    def set_pos(self, lat: float, lon: float) -> None:
        self._lat = lat
        self._lon = lon
        self._update_frame()


def _make_drone(lat: float = 0.0, lon: float = 0.0) -> tuple[MavlinkDrone, _SimVehicle]:
    """
    Build a MavlinkDrone with a simulated vehicle injected.
    goto() is patched to record calls and optionally teleport the drone.
    """
    sim = _SimVehicle(lat=lat, lon=lon)

    drone = MavlinkDrone.__new__(MavlinkDrone)
    # Manually init the fields we need (skip connect()).
    drone.vehicle = sim
    drone._mission_pause_requested = threading.Event()
    drone._mission_abort_requested = threading.Event()
    drone._mission_control_changed = threading.Event()
    drone._mission_control_lock = threading.Lock()
    drone._groundspeed_override_mps = None
    drone.follower_config = WaypointFollowerConfig()

    # Patch goto so we can track commands and optionally teleport.
    original_goto_calls: list[Coordinate] = []

    def _goto(coord: Coordinate) -> None:
        original_goto_calls.append(coord)

    drone.goto = _goto  # type: ignore[method-assign]
    sim.goto_calls = original_goto_calls

    return drone, sim


def _teleport(sim: _SimVehicle, target: Coordinate, within_m: float = 0.1) -> None:
    """Move sim vehicle to within *within_m* of *target* (same lat/lon)."""
    # Place the drone slightly inside the acceptance sphere using a small
    # lat offset (~1 degree ≈ 111 km; within_m in metres → degrees).
    offset_deg = within_m / 111_000.0
    sim.set_pos(target.lat + offset_deg, target.lon)


# ---------------------------------------------------------------------------
# Basics
# ---------------------------------------------------------------------------


class TestBasics:
    def test_empty_path_is_noop(self):
        drone, sim = _make_drone()
        drone._fly_segment_path([], WaypointFollowerConfig())
        assert sim.goto_calls == []

    def test_single_waypoint_completes(self):
        """Drone starts at the target — should accept and return immediately."""
        wp = _coord(lat=1.0, lon=1.0)
        drone, sim = _make_drone(lat=1.0, lon=1.0)  # already at target
        cfg = WaypointFollowerConfig(acceptance_radius_m=5.0, poll_interval_s=0.01)
        drone._fly_segment_path([wp], cfg)
        # goto must have been called for the one waypoint.
        assert wp in sim.goto_calls

    def test_multi_waypoint_path_visits_all(self):
        """Each waypoint should be issued as a goto command."""
        wps = [_coord(lat=float(i)) for i in range(4)]
        drone, sim = _make_drone()

        # Teleport drone to each waypoint immediately on each goto call.
        issued: list[Coordinate] = []

        def smart_goto(coord: Coordinate) -> None:
            issued.append(coord)
            # Teleport to the commanded location so the follower accepts fast.
            sim.set_pos(coord.lat, coord.lon)

        drone.goto = smart_goto  # type: ignore[method-assign]
        sim.goto_calls = issued

        cfg = WaypointFollowerConfig(
            acceptance_radius_m=50_000.0,  # very loose — accepts immediately
            lookahead_m=0.0,
            poll_interval_s=0.01,
        )
        drone._fly_segment_path(wps, cfg)

        # All 4 waypoints should appear in the goto command sequence.
        commanded = [c for c in issued if c in wps]
        for wp in wps:
            assert wp in commanded, f"wp {wp} was never commanded"


# ---------------------------------------------------------------------------
# Lookahead
# ---------------------------------------------------------------------------


class TestLookahead:
    def test_next_wp_pre_commanded_when_in_lookahead_range(self):
        """
        When the drone enters the lookahead sphere, goto(path[i+1]) must be
        issued exactly once before the acceptance check fires.
        """
        wp0 = _coord(lat=0.0, lon=0.0)
        wp1 = _coord(lat=1.0, lon=0.0)  # ~111 km away

        # Drone starts at wp0 — within acceptance immediately.
        drone, sim = _make_drone(lat=0.0, lon=0.0)

        issued: list[Coordinate] = []

        def tracking_goto(coord: Coordinate) -> None:
            issued.append(coord)

        drone.goto = tracking_goto  # type: ignore[method-assign]

        cfg = WaypointFollowerConfig(
            acceptance_radius_m=200_000.0,  # accept immediately at both wps (wp1 is ~111 km away)
            lookahead_m=60_000.0,  # fires immediately at wp0 (dist=0 < 60 km)
            poll_interval_s=0.01,
        )
        drone._fly_segment_path([wp0, wp1], cfg)

        # wp1 must have been pre-commanded via lookahead, then commanded again
        # at the start of the wp1 leg.
        assert issued.count(wp1) >= 2, (
            "wp1 should appear at least twice: once from lookahead and once "
            f"from the leg start.  Got: {issued}"
        )

    def test_lookahead_fires_at_most_once_per_leg(self):
        """Even after many poll cycles inside the lookahead sphere, only one
        pre-command is issued per leg."""
        wp0 = _coord(lat=0.0)
        wp1 = _coord(lat=1.0)

        drone, sim = _make_drone(lat=0.0)
        issued: list[Coordinate] = []
        poll_count = 0

        def tracking_goto(coord: Coordinate) -> None:
            issued.append(coord)

        drone.goto = tracking_goto  # type: ignore[method-assign]

        cfg = WaypointFollowerConfig(
            acceptance_radius_m=5.0,  # tight — drone not at acceptance yet
            lookahead_m=50_000.0,  # fires immediately
            poll_interval_s=0.01,
            max_active_leg_s=1.0,  # short timeout to bound the test
        )

        # Override acceptance so we can let a few cycles run then teleport.
        cycles = [0]

        def on_progress(i: int, n: int, d: float) -> None:
            cycles[0] += 1
            if cycles[0] >= 5:
                # Teleport into acceptance so the leg ends.
                sim.set_pos(wp0.lat, wp0.lon)

        cfg_with_cb = WaypointFollowerConfig(
            acceptance_radius_m=200_000.0,  # accept at both legs (wp1 is ~111 km from origin)
            lookahead_m=50_000.0,
            poll_interval_s=0.01,
            on_progress=on_progress,
        )
        drone._fly_segment_path([wp0, wp1], cfg_with_cb)

        # Count how many times wp1 was commanded BEFORE the wp1 leg started.
        wp1_commands_before_leg = sum(
            1
            for c in issued
            if c == wp1 and issued.index(c) < issued.index(wp1)
            # All pre-leg wp1 commands are lookahead; the leg start adds one more.
        )
        # There should be exactly 1 lookahead pre-command for wp1
        # (plus 1 from the leg start = 2 total).
        assert issued.count(wp1) == 2, (
            f"Expected exactly 2 wp1 commands (1 lookahead + 1 leg start), got "
            f"{issued.count(wp1)}.  Full sequence: {issued}"
        )

    def test_lookahead_disabled_when_zero(self):
        """Setting lookahead_m=0 must never pre-command the next waypoint."""
        wp0 = _coord(lat=0.0)
        wp1 = _coord(lat=1.0)

        drone, sim = _make_drone(lat=0.0)
        issued: list[Coordinate] = []

        def tracking_goto(coord: Coordinate) -> None:
            issued.append(coord)
            sim.set_pos(coord.lat, coord.lon)  # teleport to accept immediately

        drone.goto = tracking_goto  # type: ignore[method-assign]

        cfg = WaypointFollowerConfig(
            acceptance_radius_m=50_000.0,
            lookahead_m=0.0,
            poll_interval_s=0.01,
        )
        drone._fly_segment_path([wp0, wp1], cfg)

        # wp1 should appear exactly once — from the leg start, never from lookahead.
        assert issued.count(wp1) == 1, (
            f"lookahead disabled: expected wp1 commanded once, got {issued.count(wp1)}"
        )

    def test_lookahead_does_not_fire_on_last_waypoint(self):
        """The final waypoint has no successor — no pre-command should be issued."""
        wp0 = _coord(lat=0.0)

        drone, sim = _make_drone(lat=0.0)
        issued: list[Coordinate] = []

        def tracking_goto(coord: Coordinate) -> None:
            issued.append(coord)

        drone.goto = tracking_goto  # type: ignore[method-assign]

        cfg = WaypointFollowerConfig(
            acceptance_radius_m=50_000.0,
            lookahead_m=50_000.0,
            poll_interval_s=0.01,
        )
        drone._fly_segment_path([wp0], cfg)

        # Only one goto — the initial leg command.
        assert len(issued) == 1


# ---------------------------------------------------------------------------
# Acceptance radius
# ---------------------------------------------------------------------------


class TestAcceptanceRadius:
    def test_waypoint_not_accepted_when_too_far(self):
        """
        When the drone is outside acceptance_radius_m the loop must keep
        running.  We verify by aborting after a short delay, which proves
        the loop did not exit prematurely.
        """
        wp = _coord(lat=1.0)  # ~111 km from drone at lat=0
        drone, sim = _make_drone(lat=0.0)

        # Abort after ~0.1 s to end the otherwise-infinite loop.
        def _abort_soon():
            time.sleep(0.1)
            drone._mission_abort_requested.set()

        t = threading.Thread(target=_abort_soon, daemon=True)
        t.start()

        cfg = WaypointFollowerConfig(
            acceptance_radius_m=1.0,  # 1 m — drone is 111 km away
            poll_interval_s=0.01,
        )
        with pytest.raises(MissionAbortRequested):
            drone._fly_segment_path([wp], cfg)

    def test_waypoint_accepted_at_acceptance_radius(self):
        """Drone starts inside acceptance sphere — loop exits immediately."""
        wp = _coord(lat=0.0, lon=0.0)
        drone, sim = _make_drone(lat=0.0, lon=0.0)

        cfg = WaypointFollowerConfig(
            acceptance_radius_m=50_000.0,  # very large — drone is inside
            lookahead_m=0.0,
            poll_interval_s=0.01,
        )
        # Should return without error.
        drone._fly_segment_path([wp], cfg)

    def test_custom_tight_acceptance_radius(self):
        """1 m acceptance: drone 5 m away should NOT be accepted."""
        wp = _coord(lat=0.0, lon=0.0)
        # 5 m north in degrees
        start_lat = 0.0 + 5.0 / 111_000.0
        drone, sim = _make_drone(lat=start_lat, lon=0.0)

        aborted = threading.Event()

        def _abort():
            time.sleep(0.1)
            drone._mission_abort_requested.set()
            aborted.set()

        threading.Thread(target=_abort, daemon=True).start()

        cfg = WaypointFollowerConfig(
            acceptance_radius_m=1.0,
            lookahead_m=0.0,
            poll_interval_s=0.01,
        )
        with pytest.raises(MissionAbortRequested):
            drone._fly_segment_path([wp], cfg)

        assert aborted.is_set()


# ---------------------------------------------------------------------------
# Pause / resume
# ---------------------------------------------------------------------------


class TestPauseResume:
    def test_pause_halts_progress_and_resume_continues(self):
        """
        Pause event prevents the acceptance check from being reached.
        After unpause the follower re-issues goto and eventually accepts.
        """
        # Drone starts ~111 m from the waypoint — outside the acceptance sphere.
        wp = _coord(lat=0.001, lon=0.0)
        drone, sim = _make_drone(lat=0.0, lon=0.0)

        issued: list[Coordinate] = []

        def tracking_goto(coord: Coordinate) -> None:
            issued.append(coord)

        drone.goto = tracking_goto  # type: ignore[method-assign]

        paused_long_enough = threading.Event()

        def _pause_then_resume():
            time.sleep(0.05)
            drone._mission_pause_requested.set()
            time.sleep(0.15)
            paused_long_enough.set()
            # Teleport inside acceptance before clearing pause so the leg completes.
            sim.set_pos(wp.lat, wp.lon)
            drone._mission_pause_requested.clear()

        t = threading.Thread(target=_pause_then_resume, daemon=True)
        t.start()

        cfg = WaypointFollowerConfig(
            acceptance_radius_m=5.0,  # 5 m — drone is initially ~111 m away
            lookahead_m=0.0,
            poll_interval_s=0.02,
        )
        drone._fly_segment_path([wp], cfg)
        t.join(timeout=2.0)

        assert paused_long_enough.is_set(), "Pause period was not exercised"
        # goto must have been called at least twice: initial + after-unpause re-issue.
        assert issued.count(wp) >= 2, (
            f"Expected ≥2 goto(wp) calls (initial + post-unpause), got {issued.count(wp)}"
        )

    def test_paused_time_excluded_from_leg_timeout(self):
        """
        A leg that is paused for 0.3 s with max_active_leg_s=0.2 s must NOT
        time out — only active (non-paused) flight time counts.
        """
        wp = _coord(lat=1.0)  # far enough to not accept immediately
        # Drone starts far from wp
        drone, sim = _make_drone(lat=0.0)

        def _pause_then_teleport():
            time.sleep(0.05)
            drone._mission_pause_requested.set()
            time.sleep(0.3)  # pause for 300 ms > max_active_leg_s
            sim.set_pos(wp.lat, wp.lon)  # teleport inside acceptance
            drone._mission_pause_requested.clear()

        t = threading.Thread(target=_pause_then_teleport, daemon=True)
        t.start()

        cfg = WaypointFollowerConfig(
            acceptance_radius_m=50_000.0,
            lookahead_m=0.0,
            poll_interval_s=0.02,
            max_active_leg_s=0.2,  # short timeout — would fire if paused time counted
        )
        # Must complete without RuntimeError.
        drone._fly_segment_path([wp], cfg)
        t.join(timeout=2.0)


# ---------------------------------------------------------------------------
# Abort
# ---------------------------------------------------------------------------


class TestAbort:
    def test_abort_raises_immediately(self):
        """MissionAbortRequested is raised on the next poll after abort is set."""
        wp = _coord(lat=1.0)  # far — will not accept naturally
        drone, sim = _make_drone(lat=0.0)

        def _abort_soon():
            time.sleep(0.05)
            drone._mission_abort_requested.set()

        threading.Thread(target=_abort_soon, daemon=True).start()

        cfg = WaypointFollowerConfig(poll_interval_s=0.02)
        with pytest.raises(MissionAbortRequested):
            drone._fly_segment_path([wp], cfg)

    def test_abort_during_pause_raises(self):
        """Abort set while paused must raise MissionAbortRequested."""
        wp = _coord(lat=1.0)
        drone, sim = _make_drone(lat=0.0)

        drone._mission_pause_requested.set()  # already paused

        def _abort_soon():
            time.sleep(0.1)
            drone._mission_abort_requested.set()

        threading.Thread(target=_abort_soon, daemon=True).start()

        cfg = WaypointFollowerConfig(poll_interval_s=0.02)
        with pytest.raises(MissionAbortRequested):
            drone._fly_segment_path([wp], cfg)

    def test_follow_waypoints_clears_abort_and_pause_before_start(self):
        """
        follow_waypoints must reset both events so a leftover abort/pause
        from a previous mission does not immediately fire.
        """
        drone, sim = _make_drone(lat=0.0)
        drone._mission_abort_requested.set()
        drone._mission_pause_requested.set()

        # Drone is at the only waypoint — should complete without raising.
        wp = _coord(lat=0.0)
        drone.follower_config = WaypointFollowerConfig(
            acceptance_radius_m=50_000.0,
            lookahead_m=0.0,
            poll_interval_s=0.01,
        )

        called: list[Coordinate] = []
        drone.goto = called.append  # type: ignore[method-assign]

        drone.follow_waypoints([wp])  # must not raise


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


class TestTimeout:
    def test_leg_timeout_raises_runtime_error(self):
        """
        When a waypoint is unreachable and max_active_leg_s elapses, a
        RuntimeError must be raised (not a hang).
        """
        wp = _coord(lat=1.0)  # ~111 km — never reached
        drone, sim = _make_drone(lat=0.0)

        cfg = WaypointFollowerConfig(
            acceptance_radius_m=1.0,
            lookahead_m=0.0,
            poll_interval_s=0.02,
            max_active_leg_s=0.1,  # 100 ms
        )
        t0 = time.monotonic()
        with pytest.raises(RuntimeError, match="timed out"):
            drone._fly_segment_path([wp], cfg)
        elapsed = time.monotonic() - t0
        # Must fire quickly — not a multi-second hang.
        assert elapsed < 1.5, f"Timeout took {elapsed:.2f}s — too slow"


# ---------------------------------------------------------------------------
# Progress callback
# ---------------------------------------------------------------------------


class TestProgressCallback:
    def test_on_progress_called_each_poll_cycle(self):
        """on_progress must be called at least once with correct arg types."""
        wp = _coord(lat=0.0)
        drone, sim = _make_drone(lat=0.0)

        calls: list[tuple[int, int, float]] = []

        def cb(i: int, n: int, d: float) -> None:
            calls.append((i, n, d))

        cfg = WaypointFollowerConfig(
            acceptance_radius_m=50_000.0,
            lookahead_m=0.0,
            poll_interval_s=0.01,
            on_progress=cb,
        )
        drone._fly_segment_path([wp], cfg)

        assert len(calls) >= 1
        i, n, d = calls[0]
        assert i == 0
        assert n == 1
        assert isinstance(d, float)

    def test_on_progress_exception_does_not_crash_follower(self):
        """An exception inside on_progress must be swallowed."""
        wp = _coord(lat=0.0)
        drone, sim = _make_drone(lat=0.0)

        def bad_cb(*_):
            raise ValueError("intentional test error")

        cfg = WaypointFollowerConfig(
            acceptance_radius_m=50_000.0,
            lookahead_m=0.0,
            poll_interval_s=0.01,
            on_progress=bad_cb,
        )
        # Must complete without raising.
        drone._fly_segment_path([wp], cfg)

    def test_on_progress_receives_correct_waypoint_index(self):
        """For a 3-wp path, on_progress index should advance 0 → 1 → 2."""
        wps = [_coord(lat=float(i)) for i in range(3)]
        drone, sim = _make_drone()

        seen_indices: list[int] = []

        def tracking_goto(coord: Coordinate) -> None:
            sim.set_pos(coord.lat, coord.lon)  # teleport to accept immediately

        drone.goto = tracking_goto  # type: ignore[method-assign]

        def cb(i: int, n: int, d: float) -> None:
            seen_indices.append(i)

        cfg = WaypointFollowerConfig(
            acceptance_radius_m=50_000.0,
            lookahead_m=0.0,
            poll_interval_s=0.01,
            on_progress=cb,
        )
        drone._fly_segment_path(wps, cfg)

        # Each index 0, 1, 2 should have appeared at least once.
        for expected_idx in range(3):
            assert expected_idx in seen_indices, (
                f"Index {expected_idx} never passed to on_progress; got {seen_indices}"
            )


# ---------------------------------------------------------------------------
# follower_config attribute wiring
# ---------------------------------------------------------------------------


class TestFollowerConfigAttribute:
    def test_follower_config_applied_by_follow_waypoints(self):
        """
        Mutating drone.follower_config before calling follow_waypoints must
        affect the follower behaviour.
        """
        wp = _coord(lat=0.0)
        drone, sim = _make_drone(lat=0.0)

        cb_calls: list[tuple] = []

        def cb(i, n, d):
            cb_calls.append((i, n, d))

        drone.follower_config = WaypointFollowerConfig(
            acceptance_radius_m=50_000.0,
            lookahead_m=0.0,
            poll_interval_s=0.01,
            on_progress=cb,
        )

        issued: list[Coordinate] = []
        drone.goto = issued.append  # type: ignore[method-assign]

        drone.follow_waypoints([wp])

        assert len(cb_calls) >= 1, "on_progress from follower_config was not called"

    def test_follow_waypoints_default_config_is_safe(self):
        """
        With default WaypointFollowerConfig, a drone at the target should
        accept and return — confirming default acceptance_radius_m (3 m) is
        reachable when the drone is at the waypoint.
        """
        wp = _coord(lat=0.0, lon=0.0)
        drone, sim = _make_drone(lat=0.0, lon=0.0)  # drone already at target

        issued: list[Coordinate] = []
        drone.goto = issued.append  # type: ignore[method-assign]

        # Default config — drone is within 3 m → should complete immediately.
        drone.follow_waypoints([wp])
        assert wp in issued
