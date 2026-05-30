from backend.modules.warehouse.service.safety import evaluate_warehouse_runtime_safety


def test_safety_blocks_lost_vslam() -> None:
    decision = evaluate_warehouse_runtime_safety({"slam_tracking_ok": False})

    assert decision.safe is False
    assert decision.reason == "vslam_tracking_lost"
    assert decision.action == "return_or_land"


def test_safety_blocks_close_obstacle() -> None:
    decision = evaluate_warehouse_runtime_safety(
        {"slam_tracking_ok": True, "obstacle_distance_m": 0.2},
        min_obstacle_distance_m=0.6,
    )

    assert decision.safe is False
    assert decision.reason == "obstacle_clearance_breach"
    assert decision.action == "hover"


def test_safety_allows_healthy_runtime() -> None:
    decision = evaluate_warehouse_runtime_safety(
        {
            "slam_tracking_ok": True,
            "obstacle_distance_m": 2.0,
            "ceiling_distance_m": 1.2,
            "localization_confidence": 0.9,
        }
    )

    assert decision.safe is True
    assert decision.action == "continue"
