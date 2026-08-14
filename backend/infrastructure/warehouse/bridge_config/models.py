from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from backend.infrastructure.warehouse.bridge_config.constants import GZ_TO_ROS


@dataclass(frozen=True)
class BridgeTopicMapping:
    ros_topic_name: str
    gz_topic_name: str
    ros_type_name: str = ""
    gz_type_name: str = ""
    direction: str = GZ_TO_ROS


def bridge_config_path(ros2_ws: Path) -> Path:
    return ros2_ws / "src/drone_gz_bridge/config/warehouse_bridge.yaml"


def load_bridge_config(ros2_ws: Path) -> list[BridgeTopicMapping]:
    path = bridge_config_path(ros2_ws)
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    mappings: list[BridgeTopicMapping] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        ros_topic = str(entry.get("ros_topic_name") or "").strip()
        gz_topic = str(entry.get("gz_topic_name") or "").strip()
        if not ros_topic or not gz_topic:
            continue
        mappings.append(
            BridgeTopicMapping(
                ros_topic_name=ros_topic,
                gz_topic_name=gz_topic,
                ros_type_name=str(entry.get("ros_type_name") or "").strip(),
                gz_type_name=str(entry.get("gz_type_name") or "").strip(),
                direction=str(entry.get("direction") or GZ_TO_ROS).strip(),
            )
        )
    return mappings


def gz_to_ros_mappings(mappings: list[BridgeTopicMapping]) -> list[BridgeTopicMapping]:
    return [m for m in mappings if m.direction == GZ_TO_ROS]
