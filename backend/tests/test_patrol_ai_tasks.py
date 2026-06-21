from backend.modules.patrol.ai_tasks import (
    coerce_ai_tasks,
    detector_labels_for_tasks,
    frozenset_ai_tasks,
    live_detection_ai_task,
    map_anomaly_to_ai_task,
    yolo_detection_enabled,
)


def test_coerce_ai_tasks_defaults_when_empty():
    assert coerce_ai_tasks([]) == (
        "intruder_detection",
        "vehicle_detection",
        "fence_breach_detection",
        "motion_detection",
    )


def test_coerce_ai_tasks_deduplicates():
    assert coerce_ai_tasks(["intruder_detection", "intruder_detection"]) == (
        "intruder_detection",
    )


def test_detector_labels_for_vehicle_only():
    enabled = frozenset({"vehicle_detection"})
    assert detector_labels_for_tasks(enabled) == frozenset(
        {"car", "truck", "bus", "motorcycle", "bicycle"}
    )


def test_detector_labels_for_motion_only_skips_yolo():
    enabled = frozenset({"motion_detection"})
    assert detector_labels_for_tasks(enabled) == frozenset()
    assert yolo_detection_enabled(enabled) is False


def test_map_anomaly_to_ai_task():
    assert map_anomaly_to_ai_task("scene_motion", "") == "motion_detection"
    assert map_anomaly_to_ai_task("restricted_zone_entry", "car") == "vehicle_detection"
    assert map_anomaly_to_ai_task("restricted_zone_entry", "person") == "fence_breach_detection"
    assert map_anomaly_to_ai_task("intrusion_detected", "person") == "intruder_detection"
    assert map_anomaly_to_ai_task("loitering", "truck") == "vehicle_detection"


def test_live_detection_ai_task_respects_enabled_set():
    enabled = frozenset({"vehicle_detection"})
    assert live_detection_ai_task("car", enabled) == "vehicle_detection"
    assert live_detection_ai_task("person", enabled) is None


def test_frozenset_ai_tasks():
    assert frozenset_ai_tasks(["motion_detection"]) == frozenset({"motion_detection"})
