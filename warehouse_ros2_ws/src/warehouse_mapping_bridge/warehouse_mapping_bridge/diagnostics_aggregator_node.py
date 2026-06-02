from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from typing import Any


def main() -> None:
    import rclpy
    from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
    from rclpy.node import Node
    from rclpy.qos import QoSProfile
    from rosgraph_msgs.msg import Clock
    from std_msgs.msg import String

    class WarehouseDiagnosticsAggregator(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_diagnostics_aggregator")
            self.declare_parameter(
                "use_sim_time",
                os.getenv("WAREHOUSE_USE_SIM_TIME", "0").lower() in {"1", "true", "yes", "on"},
            )
            self.declare_parameter(
                "diagnostic_stale_after_s",
                float(os.getenv("WAREHOUSE_DIAGNOSTIC_STALE_AFTER_S", "5.0")),
            )
            self.declare_parameter(
                "clock_stale_after_s",
                float(os.getenv("WAREHOUSE_CLOCK_STALE_AFTER_S", "2.0")),
            )
            self.use_sim_time = bool(self.get_parameter("use_sim_time").value)
            self.diagnostic_stale_after_s = max(
                0.5,
                float(self.get_parameter("diagnostic_stale_after_s").value),
            )
            self.clock_stale_after_s = max(0.5, float(self.get_parameter("clock_stale_after_s").value))
            self.statuses: dict[str, tuple[float, dict[str, Any]]] = {}
            self.last_clock_s: float | None = None
            self.publisher = self.create_publisher(
                String,
                "/warehouse/mapping/diagnostics_summary",
                QoSProfile(depth=10),
            )
            self.diagnostics_publisher = self.create_publisher(
                DiagnosticArray,
                "/warehouse/mapping/diagnostics_aggregate",
                QoSProfile(depth=10),
            )
            for topic in (
                "/warehouse/mapping/diagnostics",
                "/warehouse/mapping/artifact_diagnostics",
                "/warehouse/mapping/live_map_diagnostics",
            ):
                self.create_subscription(
                    DiagnosticArray,
                    topic,
                    self.on_diagnostics,
                    QoSProfile(depth=50),
                )
            self.create_subscription(Clock, "/clock", self.on_clock, QoSProfile(depth=10))
            self.create_timer(1.0, self.publish_summary)

        def on_clock(self, _message: Clock) -> None:
            self.last_clock_s = time.monotonic()

        def on_diagnostics(self, message: DiagnosticArray) -> None:
            now = time.monotonic()
            for status in message.status:
                self.statuses[status.name] = (
                    now,
                    {
                        "level": int(status.level),
                        "message": status.message,
                        "hardware_id": status.hardware_id,
                        "values": {item.key: item.value for item in status.values},
                    },
                )

        def publish_summary(self) -> None:
            now = time.monotonic()
            active: dict[str, dict[str, Any]] = {}
            stale: list[str] = []
            worst_level = DiagnosticStatus.OK
            for name, (seen_at, payload) in sorted(self.statuses.items()):
                age = now - seen_at
                if age > self.diagnostic_stale_after_s:
                    stale.append(name)
                    continue
                payload = dict(payload)
                payload["age_s"] = round(age, 3)
                active[name] = payload
                worst_level = max(worst_level, int(payload["level"]))

            clock_age = None if self.last_clock_s is None else now - self.last_clock_s
            clock_ok = (
                not self.use_sim_time
                or (clock_age is not None and clock_age <= self.clock_stale_after_s)
            )
            if not clock_ok:
                worst_level = max(worst_level, DiagnosticStatus.ERROR)

            payload = {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "source": "warehouse_diagnostics_aggregator",
                "ready": worst_level == DiagnosticStatus.OK and not stale and clock_ok,
                "status": "ready" if worst_level == DiagnosticStatus.OK and not stale and clock_ok else "degraded",
                "use_sim_time": self.use_sim_time,
                "clock_ok": clock_ok,
                "clock_age_s": None if clock_age is None else round(clock_age, 3),
                "stale_diagnostics": stale,
                "statuses": active,
            }
            msg = String()
            msg.data = json.dumps(payload, sort_keys=True)
            self.publisher.publish(msg)

            diag = DiagnosticArray()
            diag.header.stamp = self.get_clock().now().to_msg()
            status = DiagnosticStatus()
            status.name = "warehouse_mapping_bridge/diagnostics_aggregator"
            status.hardware_id = "warehouse_mapping_bridge"
            status.level = worst_level
            status.message = payload["status"]
            status.values = [
                KeyValue(key="ready", value=str(payload["ready"]).lower()),
                KeyValue(key="use_sim_time", value=str(self.use_sim_time).lower()),
                KeyValue(key="clock_ok", value=str(clock_ok).lower()),
                KeyValue(key="clock_age_s", value="" if clock_age is None else f"{clock_age:.3f}"),
                KeyValue(key="stale_diagnostics", value=",".join(stale)),
            ]
            diag.status.append(status)
            self.diagnostics_publisher.publish(diag)

    rclpy.init()
    node = WarehouseDiagnosticsAggregator()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
