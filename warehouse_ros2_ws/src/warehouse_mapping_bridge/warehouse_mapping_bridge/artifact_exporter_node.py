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


def _copy_outputs(output_dir: Path, session_dir: Path) -> list[dict[str, object]]:
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
        dst = artifacts_dir / src.relative_to(output_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append({"path": str(dst.relative_to(session_dir)), "size_bytes": dst.stat().st_size})
    return copied


def main() -> None:
    import rclpy
    from rclpy.node import Node
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
            self.publisher = self.create_publisher(String, "/warehouse/mapping/artifacts", 10)
            self.create_timer(2.0, self.export_once)
            self.exported = False

        def export_once(self) -> None:
            artifacts = _copy_outputs(self.output_dir, self.session_dir)
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

