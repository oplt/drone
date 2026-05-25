from __future__ import annotations

import os

from backend.entrypoints.ros2.common import (
    active_mission_id,
    get_mission_runtime,
    json_message,
    post_process,
    require_ros2,
)
from backend.entrypoints.ros2.topics import ANALYSIS_OUTPUT_TOPIC, MISSION_COMPLETED_TOPIC


def main() -> None:
    require_ros2()
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String

    class ProcessingTriggerNode(Node):
        def __init__(self) -> None:
            super().__init__("processing_trigger_node")
            self.poll_interval_s = max(2.0, float(os.getenv("IRRIGATION_MISSION_POLL_S", "4.0")))
            self.analysis_publisher = self.create_publisher(String, ANALYSIS_OUTPUT_TOPIC, 10)
            self.completed_publisher = self.create_publisher(String, MISSION_COMPLETED_TOPIC, 10)
            self.already_processed = False
            self.create_timer(self.poll_interval_s, self.tick)
            self.get_logger().info(
                f"Watching mission completion and publishing {MISSION_COMPLETED_TOPIC} / {ANALYSIS_OUTPUT_TOPIC}"
            )

        def tick(self) -> None:
            mission_id_value = active_mission_id()
            if not mission_id_value or self.already_processed:
                return
            runtime = get_mission_runtime(mission_id_value)
            state = runtime.get("state")
            if state not in {"completed", "failed", "aborted"}:
                return
            self.completed_publisher.publish(
                json_message({"mission_id": mission_id_value, "state": state})
            )
            analysis = post_process(mission_id_value)
            self.analysis_publisher.publish(
                json_message(
                    {
                        "mission_id": mission_id_value,
                        "status": analysis.get("status"),
                        "capture_count": analysis.get("capture_count"),
                        "stitched_image_uri": analysis.get("stitched_image_uri"),
                    }
                )
            )
            self.already_processed = True

    rclpy.init()
    node = ProcessingTriggerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
