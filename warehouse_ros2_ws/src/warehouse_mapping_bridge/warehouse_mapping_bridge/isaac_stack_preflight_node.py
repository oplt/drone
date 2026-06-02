from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from .isaac_stack_contract import expected_topics, load_stack_commands, missing_required_commands


def main() -> None:
    import rclpy
    from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
    from rclpy.node import Node
    from rclpy.qos import QoSProfile
    from std_msgs.msg import String

    class IsaacStackPreflight(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_isaac_stack_preflight")
            self.publisher = self.create_publisher(
                String,
                "/warehouse/mapping/isaac_stack_contract",
                QoSProfile(depth=1),
            )
            self.diagnostics_publisher = self.create_publisher(
                DiagnosticArray,
                "/warehouse/mapping/diagnostics",
                QoSProfile(depth=10),
            )
            manifest_path = os.getenv("WAREHOUSE_ISAAC_PREFLIGHT_MANIFEST", "").strip()
            self.manifest_path = Path(manifest_path).expanduser() if manifest_path else None
            self.create_timer(2.0, self.publish_preflight)
            self.publish_preflight()

        def publish_preflight(self) -> None:
            commands = load_stack_commands()
            missing = missing_required_commands(commands)
            payload = {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "ready": not missing,
                "status": "ready" if not missing else "blocked",
                "source": "warehouse_isaac_stack_preflight",
                "commands": [command.to_dict() for command in commands],
                "missing_required_env": [command.env for command in missing],
                "expected_topics": expected_topics(commands),
            }
            msg = String()
            msg.data = json.dumps(payload, sort_keys=True)
            self.publisher.publish(msg)
            if self.manifest_path is not None:
                self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
                self.manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

            diag = DiagnosticArray()
            diag.header.stamp = self.get_clock().now().to_msg()
            status = DiagnosticStatus()
            status.name = "warehouse_mapping_bridge/isaac_stack_preflight"
            status.hardware_id = "warehouse_mapping_bridge"
            status.level = DiagnosticStatus.OK if not missing else DiagnosticStatus.ERROR
            status.message = payload["status"]
            status.values = [
                KeyValue(key="ready", value=str(payload["ready"]).lower()),
                KeyValue(key="missing_required_env", value=",".join(payload["missing_required_env"])),
                KeyValue(key="expected_topics", value=",".join(payload["expected_topics"])),
            ]
            diag.status.append(status)
            self.diagnostics_publisher.publish(diag)

    rclpy.init()
    node = IsaacStackPreflight()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
