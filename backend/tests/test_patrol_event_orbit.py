from __future__ import annotations

from backend.modules.patrol.geo import (
    max_orbit_radius_inside_polygon,
    point_in_polygon,
)
from backend.modules.patrol.planning import generate_event_triggered_patrol_plan


def _belgian_test_geofence() -> tuple[tuple[float, float], ...]:
    return (
        (5.3400, 50.9285),
        (5.3400, 50.9305),
        (5.3425, 50.9305),
        (5.3425, 50.9285),
    )


def test_max_orbit_radius_clamped_near_geofence_edge() -> None:
    geofence = _belgian_test_geofence()
    center_lon, center_lat = 5.34065, 50.92927
    requested = 18.0
    applied = max_orbit_radius_inside_polygon(
        center_lon,
        center_lat,
        geofence,
        requested_radius_m=requested,
        safety_margin_m=2.0,
    )
    assert applied < requested
    assert applied > 0.0


def test_event_triggered_plan_orbit_stays_inside_geofence() -> None:
    geofence = _belgian_test_geofence()
    event_lonlat = (5.340658744235307, 50.92926892125356)
    plan = generate_event_triggered_patrol_plan(
        event_lonlat,
        altitude_agl_m=30.0,
        verification_radius_m=18.0,
        geofence_polygon_lonlat=geofence,
    )

    assert plan.stats["verification_radius_applied_m"] < 18.0
    assert plan.stats["orbit_segments"] >= 3
    assert len(plan.waypoints) >= 4

    for wp in plan.waypoints:
        assert point_in_polygon(wp.lat, wp.lon, geofence)


def test_event_triggered_plan_uses_circular_orbit_not_cardinal_box() -> None:
    geofence = (
        (0.0, 0.0),
        (0.0, 0.01),
        (0.01, 0.01),
        (0.01, 0.0),
    )
    plan = generate_event_triggered_patrol_plan(
        (0.005, 0.005),
        altitude_agl_m=20.0,
        verification_radius_m=50.0,
        geofence_polygon_lonlat=geofence,
        orbit_segments=8,
    )
    # Center + 8 orbit points + return to center.
    assert len(plan.waypoints) == 10
    center = plan.waypoints[0]
    orbit_points = plan.waypoints[1:-1]
    distances_m = []
    for wp in orbit_points:
        dx = (wp.lon - center.lon) * 111_320.0 * 0.999  # rough at this latitude
        dy = (wp.lat - center.lat) * 111_132.0
        distances_m.append((dx * dx + dy * dy) ** 0.5)
    assert len({round(d, 1) for d in distances_m}) == 1
