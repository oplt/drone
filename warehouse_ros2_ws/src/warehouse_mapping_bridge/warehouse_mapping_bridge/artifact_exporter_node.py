from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _copy_outputs(
    output_dir: Path,
    session_dir: Path,
    copied_state: dict[str, tuple[int, int]],
) -> list[dict[str, object]]:
    copied: list[dict[str, object]] = []
    if not output_dir.exists():
        return copied
    allowed = {
        ".glb",
        ".gltf",
        ".obj",
        ".ply",
        ".pcd",
        ".las",
        ".laz",
        ".e57",
        ".json",
        ".db3",
        ".mcap",
    }
    artifacts_dir = session_dir / "artifacts"
    for src in output_dir.rglob("*"):
        if not src.is_file() or src.suffix.lower() not in allowed:
            continue
        stat = src.stat()
        state_key = str(src.resolve())
        state_value = (stat.st_size, int(stat.st_mtime_ns))
        if copied_state.get(state_key) == state_value:
            continue
        dst = artifacts_dir / src.relative_to(output_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied_state[state_key] = state_value
        copied.append({"path": str(dst.relative_to(session_dir)), "size_bytes": dst.stat().st_size})
    return copied


def main() -> None:
    import rclpy
    from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
    from rclpy.node import Node
    from rclpy.qos import QoSProfile
    from std_msgs.msg import String

    class WarehouseArtifactExporter(Node):
        def __init__(self) -> None:
            super().__init__("warehouse_artifact_exporter")
            self.session_dir = Path(
                os.getenv("WAREHOUSE_ACTIVE_SESSION_DIR", "/tmp/warehouse_mapping_session")
            ).resolve()
            self.output_dir = Path(
                os.getenv("WAREHOUSE_ISAAC_OUTPUT_DIR", str(self.session_dir / "isaac_outputs"))
            ).resolve()
            self.flight_id = os.getenv("WAREHOUSE_ACTIVE_FLIGHT_ID", "unknown")
            self.profile = os.getenv("WAREHOUSE_ROS_PROFILE", "isaac_ros_nvblox_stereo")
            artifact_topic = os.getenv("WAREHOUSE_ARTIFACT_TOPIC", "/warehouse/mapping/artifacts")
            self.declare_parameter("artifact_topic", artifact_topic)
            self.publisher = self.create_publisher(
                String,
                str(self.get_parameter("artifact_topic").value or artifact_topic),
                QoSProfile(depth=10),
            )
            self.diagnostics_publisher = self.create_publisher(
                DiagnosticArray,
                "/warehouse/mapping/artifact_diagnostics",
                QoSProfile(depth=10),
            )
            self.copied_state: dict[str, tuple[int, int]] = {}
            period_s = float(os.getenv("WAREHOUSE_ARTIFACT_EXPORT_PERIOD_S", "10.0"))
            self.create_timer(max(1.0, period_s), self.export_once)
            self.exported = False

        def export_once(self) -> None:
            artifacts = _copy_outputs(self.output_dir, self.session_dir, self.copied_state)
            manifest = {
                "flight_id": self.flight_id,
                "profile": self.profile,
                "generated_at": _now(),
                "session_dir": str(self.session_dir),
                "source_output_dir": str(self.output_dir),
                "artifacts": artifacts,
                "metadata_files": [
                    "warehouse_mapping_manifest.json",
                    "capture_metadata.json",
                    "mapping_health_summary.json",
                ],
            }
            _write_json(self.session_dir / "artifact_index.json", manifest)
            msg = String()
            msg.data = json.dumps(manifest, sort_keys=True)
            self.publisher.publish(msg)
            diag = DiagnosticArray()
            diag.header.stamp = self.get_clock().now().to_msg()
            status = DiagnosticStatus()
            status.name = "warehouse_mapping_bridge/artifact_exporter"
            status.hardware_id = "warehouse_mapping_bridge"
            status.level = DiagnosticStatus.OK
            status.message = "exported" if artifacts else "idle"
            status.values = [
                KeyValue(key="flight_id", value=self.flight_id),
                KeyValue(key="profile", value=self.profile),
                KeyValue(key="artifact_count", value=str(len(artifacts))),
                KeyValue(key="session_dir", value=str(self.session_dir)),
            ]
            diag.status.append(status)
            self.diagnostics_publisher.publish(diag)
            self.exported = True

    rclpy.init()
    node = WarehouseArtifactExporter()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
