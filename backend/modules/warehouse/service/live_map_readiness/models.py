"""Warehouse live-map readiness — models."""

from __future__ import annotations

from dataclasses import dataclass, field

from .constants import TopicBridgeKind


@dataclass
class TopicTypeProbe:
    topic: str
    present: bool
    message_type: str | None = None
    bridge_kind: TopicBridgeKind = "missing"
    ok_for_pointcloud_bridge: bool = False
    warning: str | None = None
    info: str | None = None


@dataclass
class MappingReadinessResult:
    ready: bool
    missing_topics: list[str] = field(default_factory=list)
    topic_probes: list[TopicTypeProbe] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rgbd_pointcloud_topic: str | None = None
    rgbd_input_topics_ready: bool = False
    nvblox_pointcloud_topics: list[str] = field(default_factory=list)
    timing_ms: dict[str, int] = field(default_factory=dict)

    def readiness_flags(self) -> dict[str, bool]:
        probes_by_topic = {probe.topic: probe for probe in self.topic_probes}
        rgbd_pc_probe = probes_by_topic.get(self.rgbd_pointcloud_topic) if self.rgbd_pointcloud_topic else None
        return {
            "rgbd_input_ready": self.rgbd_input_topics_ready,
            "rgbd_colored_pointcloud_ready": bool(
                rgbd_pc_probe is not None and rgbd_pc_probe.ok_for_pointcloud_bridge
            ),
            "nvblox_esdf_ready": any(
                probe.topic.endswith("static_esdf_pointcloud") and probe.ok_for_pointcloud_bridge
                for probe in self.topic_probes
            ),
            "nvblox_color_layer_present": any(
                probe.topic.endswith("color_layer") and probe.present
                for probe in self.topic_probes
            ),
            "nvblox_tsdf_layer_present": any(
                probe.topic.endswith("tsdf_layer") and probe.present
                for probe in self.topic_probes
            ),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "missing_topics": list(self.missing_topics),
            "warnings": list(self.warnings),
            "rgbd_pointcloud_topic": self.rgbd_pointcloud_topic,
            "rgbd_input_topics_ready": self.rgbd_input_topics_ready,
            "nvblox_pointcloud_topics": list(self.nvblox_pointcloud_topics),
            "readiness_flags": self.readiness_flags(),
            "timing_ms": dict(self.timing_ms),
        }


@dataclass(frozen=True)
class StructureInputReadiness:
    esdf_topic: str | None = None
    esdf_message_received: bool = False
    esdf_message_text: str | None = None
    occupancy_topic: str | None = None
    occupancy_message_received: bool = False
    occupancy_message: dict[str, object] | None = None

    @property
    def esdf_available(self) -> bool:
        return bool(self.esdf_topic and self.esdf_message_received)

    @property
    def occupancy_available(self) -> bool:
        return bool(self.occupancy_topic and self.occupancy_message_received)

    def to_dict(self) -> dict[str, object]:
        return {
            "esdf_available": self.esdf_available,
            "esdf_topic": self.esdf_topic,
            "esdf_message_received": self.esdf_message_received,
            "occupancy_available": self.occupancy_available,
            "occupancy_topic": self.occupancy_topic,
            "occupancy_message_received": self.occupancy_message_received,
            "missing_esdf_topic": not self.esdf_available,
            "missing_occupancy_grid": not self.occupancy_available,
        }
