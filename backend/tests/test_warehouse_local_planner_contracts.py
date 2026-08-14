"""Characterization tests for warehouse local scan planning before file-size splits."""

from __future__ import annotations

from backend.modules.warehouse.planning.local_planner import plan_warehouse_scan


def test_plan_warehouse_scan_rectangular_footprint_is_stable() -> None:
    polygon = [(0.0, 0.0), (20.0, 0.0), (20.0, 12.0), (0.0, 12.0)]
    plan = plan_warehouse_scan(
        polygon_local_m=polygon,
        base_height_m=4.0,
        corridor_spacing_m=2.0,
        aisle_axis_deg=0.0,
        clearance_m=0.6,
        perimeter_offset_m=0.5,
        scan_pattern="aisle_serpentine",
        lane_strategy="serpentine",
        view_mode="forward",
        layer_count=1,
        layer_spacing_m=1.2,
        ceiling_height_m=8.0,
        ceiling_margin_m=0.7,
        max_waypoints=2500,
        max_route_m=15000.0,
    )

    assert len(plan.segments) == 12
    assert len(plan.corridors) == 5
    assert sum(1 for segment in plan.segments if segment.work_leg) == 5
    assert [segment.leg_type for segment in plan.segments] == [
        "dock_depart",
        "scan",
        "transit",
        "scan",
        "transit",
        "scan",
        "transit",
        "scan",
        "transit",
        "scan",
        "staging_return",
        "dock_return",
    ]
    assert plan.stats["route_m"] == 118.72
    assert plan.stats["aisle_axis_deg"] == 0.0
    assert plan.dock_inferred is True
    assert [layer.z_m for layer in plan.scan_layers] == [4.0]


def test_plan_warehouse_scan_rejects_empty_footprint_after_inset() -> None:
    polygon = [(0.0, 0.0), (0.4, 0.0), (0.4, 0.4), (0.0, 0.4)]
    try:
        plan_warehouse_scan(
            polygon_local_m=polygon,
            base_height_m=4.0,
            corridor_spacing_m=2.0,
            aisle_axis_deg=None,
            clearance_m=0.6,
            perimeter_offset_m=0.5,
            scan_pattern="aisle_serpentine",
            lane_strategy="serpentine",
            view_mode="forward",
            layer_count=1,
            layer_spacing_m=1.2,
            ceiling_height_m=8.0,
            ceiling_margin_m=0.7,
            max_waypoints=2500,
            max_route_m=15000.0,
        )
    except ValueError as exc:
        assert "empty" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError for unusable warehouse footprint")
