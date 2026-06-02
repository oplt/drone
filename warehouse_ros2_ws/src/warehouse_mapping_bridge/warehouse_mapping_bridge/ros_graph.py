from __future__ import annotations

import os
import time


def rclpy_topic_names(*, timeout_s: float = 0.5) -> set[str] | None:
    try:
        import rclpy
    except Exception:
        return None

    started_here = False
    node = None
    try:
        if not rclpy.ok():
            rclpy.init(args=None)
            started_here = True
        node = rclpy.create_node(
            "warehouse_graph_probe",
            namespace=os.getenv("WAREHOUSE_GRAPH_PROBE_NAMESPACE", ""),
        )
        deadline = time.monotonic() + max(0.05, timeout_s)
        topics: set[str] = set()
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            topics = {name for name, _types in node.get_topic_names_and_types()}
            if topics:
                break
        return topics
    except Exception:
        return None
    finally:
        if node is not None:
            node.destroy_node()
        if started_here and rclpy.ok():
            rclpy.shutdown()
