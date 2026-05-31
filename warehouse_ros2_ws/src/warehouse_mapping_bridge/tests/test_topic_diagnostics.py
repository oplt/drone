from __future__ import annotations

from warehouse_mapping_bridge.topic_diagnostics import (
    TopicDiagnostic,
    _message_age_is_fresh,
    summarize_diagnostics,
)


def test_message_age_ignores_sim_time_stamps() -> None:
    assert _message_age_is_fresh(None, max_age_s=3.0) is True
    assert _message_age_is_fresh(120.0, max_age_s=3.0) is False


def test_summarize_accepts_dict_diagnostics() -> None:
    summary = summarize_diagnostics(
        {
            "rgb_image": {
                "key": "rgb_image",
                "expected": "/warehouse/front/rgbd/image",
                "matched": "/warehouse/front/rgbd/image",
                "listed": True,
                "publisher_count": 0,
                "publishing": True,
                "hz": 10.0,
                "healthy": True,
                "readiness_state": "shallow_present",
            },
        }
    )
    assert "rgb_image" in summary["topic_matches"]
    assert summary["topic_matches"]["rgb_image"]["healthy"] is True


def test_summarize_marks_sensor_ready_from_hz_not_publisher_count() -> None:
    diagnostics = {
        "rgb_image": TopicDiagnostic(
            key="rgb_image",
            expected="/warehouse/front/rgbd/image",
            matched="/warehouse/front/rgbd/image",
            listed=True,
            publisher_count=0,
            publishing=True,
            hz=12.9,
            last_message_age_s=None,
            healthy=True,
            readiness_state="ok_via_messages",
        ),
        "depth": TopicDiagnostic(
            key="depth",
            expected="/warehouse/front/rgbd/depth_image",
            matched="/warehouse/front/rgbd/depth_image",
            listed=True,
            publisher_count=0,
            publishing=True,
            hz=12.9,
            last_message_age_s=None,
            healthy=True,
        ),
        "raw_lidar": TopicDiagnostic(
            key="raw_lidar",
            expected="/warehouse/front/rgbd/points",
            matched="/warehouse/front/rgbd/points",
            listed=True,
            publisher_count=0,
            publishing=True,
            hz=9.5,
            last_message_age_s=None,
            healthy=True,
        ),
        "visual_slam_odom": TopicDiagnostic(
            key="visual_slam_odom",
            expected="/warehouse/drone/odometry",
            matched="/warehouse/drone/odometry",
            listed=True,
            publisher_count=0,
            publishing=True,
            hz=40.0,
            last_message_age_s=None,
            healthy=True,
        ),
        "local_odometry": TopicDiagnostic(
            key="local_odometry",
            expected="/warehouse/local_odometry",
            matched="/warehouse/local_odometry",
            listed=True,
            publisher_count=0,
            publishing=True,
            hz=33.0,
            last_message_age_s=None,
            healthy=True,
        ),
        "imu": TopicDiagnostic(
            key="imu",
            expected="/imu",
            matched="/imu",
            listed=True,
            publisher_count=0,
            publishing=True,
            hz=100.0,
            last_message_age_s=None,
            healthy=True,
        ),
    }
    summary = summarize_diagnostics(diagnostics)
    assert summary["missing_required_topics"] == []


def test_imu_resolves_from_gazebo_graph_topic() -> None:
    from warehouse_mapping_bridge.topic_diagnostics import _fast_resolve_topic_from_graph

    listed = {
        "/warehouse/front/rgbd/image",
        "/world/iris_warehouse/model/iris_rplidar_rgbd/model/iris_with_standoffs/link/imu_link/sensor/imu_sensor/imu",
    }
    matched = _fast_resolve_topic_from_graph("imu", "/imu", listed)
    assert matched is not None
    assert matched.endswith("/imu")


def test_summarize_treats_shallow_present_as_not_missing() -> None:
    diagnostics = {
        "rgb_image": TopicDiagnostic(
            key="rgb_image",
            expected="/warehouse/front/rgbd/image",
            matched="/warehouse/front/rgbd/image",
            listed=True,
            publisher_count=0,
            publishing=False,
            hz=None,
            last_message_age_s=None,
            healthy=True,
            readiness_state="shallow_present",
        ),
        "depth": TopicDiagnostic(
            key="depth",
            expected="/warehouse/front/rgbd/depth_image",
            matched="/warehouse/front/rgbd/depth_image",
            listed=True,
            publisher_count=0,
            publishing=False,
            hz=None,
            last_message_age_s=None,
            healthy=True,
            readiness_state="shallow_present",
        ),
        "raw_lidar": TopicDiagnostic(
            key="raw_lidar",
            expected="/warehouse/front/rgbd/points",
            matched="/warehouse/front/rgbd/points",
            listed=True,
            publisher_count=0,
            publishing=False,
            hz=None,
            last_message_age_s=None,
            healthy=True,
            readiness_state="shallow_present",
        ),
        "visual_slam_odom": TopicDiagnostic(
            key="visual_slam_odom",
            expected="/warehouse/drone/odometry",
            matched="/warehouse/drone/odometry",
            listed=True,
            publisher_count=0,
            publishing=False,
            hz=None,
            last_message_age_s=None,
            healthy=True,
            readiness_state="shallow_present",
        ),
        "local_odometry": TopicDiagnostic(
            key="local_odometry",
            expected="/warehouse/local_odometry",
            matched="/warehouse/local_odometry",
            listed=True,
            publisher_count=0,
            publishing=False,
            hz=None,
            last_message_age_s=None,
            healthy=True,
            readiness_state="shallow_present",
        ),
        "imu": TopicDiagnostic(
            key="imu",
            expected="/imu",
            matched="/imu",
            listed=True,
            publisher_count=0,
            publishing=False,
            hz=None,
            last_message_age_s=None,
            healthy=True,
            readiness_state="shallow_present",
        ),
        "pointcloud": TopicDiagnostic(
            key="pointcloud",
            expected="/nvblox_node/static_esdf_pointcloud",
            matched="/nvblox_node/static_esdf_pointcloud",
            listed=True,
            publisher_count=0,
            publishing=False,
            hz=None,
            last_message_age_s=None,
            healthy=True,
            readiness_state="shallow_present",
        ),
    }
    summary = summarize_diagnostics(diagnostics)
    assert summary["missing_required_topics"] == []
    assert summary["missing_nvblox_topics"] == []
