from __future__ import annotations

from pathlib import Path


def test_gazebo_sensor_bridge_bridges_native_topics_only() -> None:
    script = Path("scripts/start_gazebo_sensor_bridge.sh").read_text(encoding="utf-8")

    assert "_gz_bridge_specs=(" in script
    assert "${RGB_TOPIC}@sensor_msgs/msg/Image" in script
    assert "${ODOM_TOPIC}@nav_msgs/msg/Odometry" in script
    assert "/warehouse/contract/rgb/image@sensor_msgs" not in script
    assert "/warehouse/contract/odometry@nav_msgs" not in script
    assert "ros2 run topic_tools relay" not in script
    assert "warehouse_topic_adapter" in script
    assert "ros_gz_bridge pid=" in script
    assert "wait -n" not in script
