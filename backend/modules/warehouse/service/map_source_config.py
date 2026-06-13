from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LiveMapLayerId = Literal[
    "mid360_lidar",
    "rgbd_colored",
    "nvblox_color",
    "nvblox_esdf",
    "nvblox_tsdf",
    "nvblox_mesh",
]

LiveMapSourceId = Literal[
    "mid360_raw",
    "rgbd_colored",
    "nvblox_color",
    "nvblox_esdf",
    "nvblox_tsdf",
    "nvblox_mesh",
    "odom",
]


@dataclass(frozen=True)
class LiveMapSourceConfig:
    source_id: LiveMapSourceId
    topic: str
    layer: LiveMapLayerId
    chunk_prefix: str
    chunk_sequence_width: int
    global_frame: str
    max_points: int
    min_publish_interval_s: float
    colored: bool
    kind: Literal["point_cloud", "mesh", "esdf", "costmap", "occupancy"] = "point_cloud"


WAREHOUSE_LIVE_MAP_SOURCES: dict[LiveMapSourceId, LiveMapSourceConfig] = {
    "mid360_raw": LiveMapSourceConfig(
        source_id="mid360_raw",
        topic="/warehouse/mid360/points",
        layer="mid360_lidar",
        chunk_prefix="mid360",
        chunk_sequence_width=6,
        global_frame="odom",
        max_points=30_000,
        min_publish_interval_s=0.75,
        colored=False,
        kind="point_cloud",
    ),
    "rgbd_colored": LiveMapSourceConfig(
        source_id="rgbd_colored",
        topic="/warehouse/front/rgbd/points",
        layer="rgbd_colored",
        chunk_prefix="rgbd",
        chunk_sequence_width=6,
        global_frame="odom",
        max_points=25_000,
        min_publish_interval_s=0.5,
        colored=True,
        kind="point_cloud",
    ),
    "nvblox_color": LiveMapSourceConfig(
        source_id="nvblox_color",
        # Integrated color voxels (nvblox_msgs/VoxelBlockLayer) in global_frame.
        # Captured by nvblox_layers_live_map_bridge — not back_projected_depth.
        topic="/nvblox_node/color_layer",
        layer="nvblox_color",
        chunk_prefix="nvblox_color",
        chunk_sequence_width=6,
        global_frame="odom",
        max_points=20_000,
        min_publish_interval_s=1.0,
        colored=True,
        kind="point_cloud",
    ),
    "nvblox_esdf": LiveMapSourceConfig(
        source_id="nvblox_esdf",
        topic="/nvblox_node/static_esdf_pointcloud",
        layer="nvblox_esdf",
        chunk_prefix="nvblox_esdf",
        chunk_sequence_width=8,
        global_frame="odom",
        max_points=15_000,
        min_publish_interval_s=1.0,
        colored=True,
        kind="esdf",
    ),
    "nvblox_tsdf": LiveMapSourceConfig(
        source_id="nvblox_tsdf",
        # Internal nvblox layer blocks (nvblox_msgs/VoxelBlockLayer), not PointCloud2.
        topic="/nvblox_node/tsdf_layer",
        layer="nvblox_tsdf",
        chunk_prefix="nvblox_tsdf",
        chunk_sequence_width=6,
        global_frame="odom",
        max_points=15_000,
        min_publish_interval_s=1.0,
        colored=True,
        kind="point_cloud",
    ),
    "nvblox_mesh": LiveMapSourceConfig(
        source_id="nvblox_mesh",
        topic="/nvblox_node/mesh",
        layer="nvblox_mesh",
        chunk_prefix="nvblox_mesh",
        chunk_sequence_width=6,
        global_frame="odom",
        max_points=0,
        min_publish_interval_s=2.0,
        colored=False,
        kind="mesh",
    ),
    "odom": LiveMapSourceConfig(
        source_id="odom",
        topic="/warehouse/drone/odometry",
        layer="mid360_lidar",
        chunk_prefix="odom",
        chunk_sequence_width=6,
        global_frame="odom",
        max_points=0,
        min_publish_interval_s=0.5,
        colored=False,
        kind="point_cloud",
    ),
}

ODOM_PREFLIGHT_TOPICS: tuple[str, ...] = ("/warehouse/drone/odometry",)

NVBLOX_INTERNAL_LAYER_TOPICS: tuple[str, ...] = (
    "/nvblox_node/color_layer",
    "/nvblox_node/tsdf_layer",
)

NVBLOX_REQUIRED_POINTCLOUD_TOPICS: tuple[str, ...] = (
    "/nvblox_node/static_esdf_pointcloud",
)

NVBLOX_OPTIONAL_ESDF_TOPICS: tuple[str, ...] = (
    "/nvblox_node/pessimistic_static_esdf_pointcloud",
    "/nvblox_node/combined_esdf_pointcloud",
    "/nvblox_node/dynamic_esdf_pointcloud",
)

NVBLOX_POINTCLOUD_OUTPUT_TOPICS: tuple[str, ...] = (
    *NVBLOX_REQUIRED_POINTCLOUD_TOPICS,
    *NVBLOX_OPTIONAL_ESDF_TOPICS,
)

RGBD_VISUALIZATION_TOPIC: str = "/warehouse/front/rgbd/points"

NVBLOX_OUTPUT_TOPICS: tuple[str, ...] = (
    *NVBLOX_INTERNAL_LAYER_TOPICS,
    *NVBLOX_POINTCLOUD_OUTPUT_TOPICS,
    "/nvblox_node/mesh",
    "/nvblox_node/mesh_marker",
    "/nvblox_node/static_map_slice",
    "/nvblox_node/static_occupancy_grid",
)

RGBD_INPUT_TOPICS: tuple[str, ...] = (
    "/warehouse/front/rgbd/image",
    "/warehouse/front/rgbd/depth_image",
    "/warehouse/front/rgbd/camera_info",
    *ODOM_PREFLIGHT_TOPICS,
)

RGBD_POINTCLOUD_CANDIDATE_PREFIXES: tuple[str, ...] = (
    "/warehouse/front/rgbd/points",
    "/nvblox_node/back_projected_depth/",
)

RGBD_PREFLIGHT_TOPICS: tuple[str, ...] = (
    "/warehouse/front/rgbd/points",
    *RGBD_INPUT_TOPICS[0:3],
)

LIDAR_PREFLIGHT_TOPICS: tuple[str, ...] = ("/warehouse/mid360/points",)


def chunk_id_for_source(source: LiveMapSourceConfig, sequence: int) -> str:
    return f"{source.chunk_prefix}_{sequence:0{source.chunk_sequence_width}d}"


def source_by_layer(layer: LiveMapLayerId) -> LiveMapSourceConfig | None:
    for entry in WAREHOUSE_LIVE_MAP_SOURCES.values():
        if entry.layer == layer:
            return entry
    return None
