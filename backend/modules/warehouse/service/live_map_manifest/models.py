"""Live-map flight manifest — manifest model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LiveMapFlightManifest:
    flight_id: str
    generated_at: str
    chunk_counts: dict[str, int] = field(default_factory=dict)
    point_counts: dict[str, int] = field(default_factory=dict)
    rgbd_colored_available: bool = False
    rgbd_cloud_available: bool = False
    rgbd_has_rgb: bool = False
    nvblox_available: bool = False
    raw_lidar_only: bool = False
    localization_ok: bool = True
    localization_quality: str = "ok"
    quality_evidence: bool = False
    missing_topics: list[str] = field(default_factory=list)
    map_quality: str = "unknown"
    default_view_layer: str | None = None
    diagnostic_nvblox_layers: list[str] = field(default_factory=list)
    esdf_available: bool = False
    esdf_topic: str | None = None
    esdf_pointcloud_path: str | None = None
    occupancy_available: bool = False
    occupancy_topic: str | None = None
    occupancy_grid_path: str | None = None
    frame_id: str = "odom"
    coordinate_frame: str = "odom"
    source_quality: dict[str, dict[str, Any]] = field(default_factory=dict)
    chunk_quality: list[dict[str, Any]] = field(default_factory=list)
    rack_face_coverage: dict[str, Any] = field(default_factory=dict)
    coverage_repair: dict[str, Any] = field(default_factory=dict)
    tf_degraded: bool = False
    tf_jump_back_count: int = 0
    tf_old_data_count: int = 0
    nvblox_restart_count: int = 0
    diagnostics_phase: str = "pre_finalize"
    manifest_status: str = "complete"
    missing_chunks: list[str] = field(default_factory=list)
    total_bytes: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "flight_id": self.flight_id,
            "generated_at": self.generated_at,
            "chunk_counts": dict(self.chunk_counts),
            "point_counts": dict(self.point_counts),
            "rgbd_colored_available": self.rgbd_colored_available,
            "rgbd_cloud_available": self.rgbd_cloud_available,
            "rgbd_has_rgb": self.rgbd_has_rgb,
            "nvblox_available": self.nvblox_available,
            "raw_lidar_only": self.raw_lidar_only,
            "localization_ok": self.localization_ok,
            "localization_quality": self.localization_quality,
            "quality_evidence": self.quality_evidence,
            "missing_topics": list(self.missing_topics),
            "map_quality": self.map_quality,
            "default_view_layer": self.default_view_layer,
            "diagnostic_nvblox_layers": list(self.diagnostic_nvblox_layers),
            "esdf_available": self.esdf_available,
            "esdf_topic": self.esdf_topic,
            "esdf_pointcloud_path": self.esdf_pointcloud_path,
            "occupancy_available": self.occupancy_available,
            "occupancy_topic": self.occupancy_topic,
            "occupancy_grid_path": self.occupancy_grid_path,
            "frame_id": self.frame_id,
            "coordinate_frame": self.coordinate_frame,
            "source_quality": dict(self.source_quality),
            "chunk_quality": list(self.chunk_quality),
            "rack_face_coverage": dict(self.rack_face_coverage),
            "coverage_repair": dict(self.coverage_repair),
            "tf_degraded": bool(self.tf_degraded),
            "tf_jump_back_count": int(self.tf_jump_back_count),
            "tf_old_data_count": int(self.tf_old_data_count),
            "nvblox_restart_count": int(self.nvblox_restart_count),
            "diagnostics_phase": self.diagnostics_phase,
            "manifest_status": self.manifest_status,
            "missing_chunks": list(self.missing_chunks),
            "total_bytes": int(self.total_bytes),
        }


__all__ = ["LiveMapFlightManifest"]
