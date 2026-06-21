from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.modules.warehouse.service.live_map_readiness import (
    _rgb_inputs_ready,
    classify_topic_for_bridge,
    discover_rgbd_pointcloud_topics,
    probe_mapping_tf_degraded,
)
from backend.modules.warehouse.service.readiness_result import (
    readiness_from_perception_status_strict,
)


def test_classify_internal_nvblox_layer_as_info_not_error() -> None:
    probe = classify_topic_for_bridge(
        topic="/nvblox_node/color_layer",
        present=True,
        message_type="nvblox_msgs/msg/VoxelBlockLayer",
        expect_pointcloud2=False,
        internal_layer=True,
    )
    assert probe.bridge_kind == "internal_layer"
    assert probe.ok_for_pointcloud_bridge is False
    assert probe.warning is None
    assert probe.info is not None


def test_classify_esdf_pointcloud_as_bridgeable() -> None:
    probe = classify_topic_for_bridge(
        topic="/nvblox_node/static_esdf_pointcloud",
        present=True,
        message_type="sensor_msgs/msg/PointCloud2",
        expect_pointcloud2=True,
    )
    assert probe.ok_for_pointcloud_bridge is True
    assert probe.bridge_kind == "pointcloud2"


def test_resolve_colored_bridge_uses_back_projection_only_for_rgbd_fallback() -> None:
    from backend.modules.warehouse.service.live_map_readiness import (
        resolve_colored_bridge_sources,
    )
    topics = {
        "/warehouse/front/rgbd/points",
        "/nvblox_node/static_esdf_pointcloud",
        "/nvblox_node/back_projected_depth/iris_rplidar_rgbd/front_rgbd_camera_link/front_rgbd_camera",
    }
    topic_types = {
        "/warehouse/front/rgbd/points": "sensor_msgs/msg/PointCloud2",
        "/nvblox_node/static_esdf_pointcloud": "sensor_msgs/msg/PointCloud2",
        "/nvblox_node/back_projected_depth/iris_rplidar_rgbd/front_rgbd_camera_link/front_rgbd_camera": "sensor_msgs/msg/PointCloud2",
    }

    def _fake_probe(*, topics: set[str], quiet: bool = False):
        del quiet
        return {}, topic_types

    import backend.modules.warehouse.service.live_map_readiness as readiness

    original = readiness.probe_live_map_topic_types
    readiness.probe_live_map_topic_types = _fake_probe
    try:
        sources = resolve_colored_bridge_sources(topics=topics)
    finally:
        readiness.probe_live_map_topic_types = original

    assert "rgbd_colored" in sources
    assert "nvblox_esdf" in sources
    assert "nvblox_color" not in sources
    assert sources["rgbd_colored"].topic == "/warehouse/front/rgbd/points"


def test_resolve_colored_bridge_rgbd_fallback_to_back_projection() -> None:
    from backend.modules.warehouse.service.live_map_readiness import (
        resolve_colored_bridge_sources,
    )
    back_topic = (
        "/nvblox_node/back_projected_depth/iris_rplidar_rgbd/front_rgbd_camera_link/front_rgbd_camera"
    )
    topics = {back_topic, "/nvblox_node/static_esdf_pointcloud"}
    topic_types = {
        back_topic: "sensor_msgs/msg/PointCloud2",
        "/nvblox_node/static_esdf_pointcloud": "sensor_msgs/msg/PointCloud2",
    }

    def _fake_probe(*, topics: set[str], quiet: bool = False):
        del quiet
        return {}, topic_types

    import backend.modules.warehouse.service.live_map_readiness as readiness

    original = readiness.probe_live_map_topic_types
    readiness.probe_live_map_topic_types = _fake_probe
    try:
        sources = resolve_colored_bridge_sources(topics=topics)
    finally:
        readiness.probe_live_map_topic_types = original

    assert "rgbd_colored" in sources
    assert sources["rgbd_colored"].topic == back_topic
    assert "nvblox_color" not in sources


def test_resolve_nvblox_layers_uses_static_map_slice_as_occupancy() -> None:
    from backend.modules.warehouse.service.nvblox_layers_live_map_bridge import (
        resolve_nvblox_layer_bridge_sources,
    )

    topics = {"/nvblox_node/static_map_slice"}
    topic_types = {"/nvblox_node/static_map_slice": "nav_msgs/msg/OccupancyGrid"}

    def _fake_probe(*, topics: set[str], quiet: bool = False):
        del quiet
        return {}, topic_types

    import backend.modules.warehouse.service.live_map_readiness as readiness

    original = readiness.probe_live_map_topic_types
    readiness.probe_live_map_topic_types = _fake_probe
    try:
        sources = resolve_nvblox_layer_bridge_sources(topics=topics)
    finally:
        readiness.probe_live_map_topic_types = original

    assert sources["nvblox_occupancy"].topic == "/nvblox_node/static_map_slice"


def test_discover_rgbd_prefers_warehouse_points_topic() -> None:
    topics = {
        "/nvblox_node/back_projected_depth/camera",
        "/warehouse/front/rgbd/points",
    }
    discovered = discover_rgbd_pointcloud_topics(topics)
    assert discovered[0] == "/warehouse/front/rgbd/points"


def test_rgb_inputs_ready_without_points_topic() -> None:
    topics = {
        "/warehouse/front/rgbd/image",
        "/warehouse/front/rgbd/depth_image",
        "/warehouse/front/rgbd/camera_info",
        "/warehouse/drone/odometry",
    }
    ready, missing = _rgb_inputs_ready(topics, topics)
    assert ready is True
    assert missing == []

def test_rgb_inputs_not_ready_when_camera_topics_missing() -> None:
    topics = {"/warehouse/drone/odometry"}
    ready, missing = _rgb_inputs_ready(topics, topics)
    assert ready is False
    assert "/warehouse/front/rgbd/image" in missing


def test_core_sensors_do_not_require_disabled_raw_lidar(monkeypatch) -> None:
    from backend.infrastructure.warehouse import bridge_config

    monkeypatch.setattr(
        bridge_config.settings,
        "warehouse_live_map_raw_lidar_enabled",
        False,
    )
    monkeypatch.setattr(
        bridge_config.settings,
        "warehouse_include_raw_lidar_preview",
        False,
    )
    monkeypatch.setattr(
        bridge_config.settings,
        "warehouse_persist_raw_lidar_layer",
        False,
    )

    components = bridge_config.bridge_probe_to_components(
        {
            "listed_ros_topics": [
                "/warehouse/drone/odometry",
                "/warehouse/front/rgbd/image",
                "/warehouse/front/rgbd/depth_image",
                "/warehouse/imu",
            ],
            "odometry_topic": "/warehouse/drone/odometry",
            "rgb_topic": "/warehouse/front/rgbd/image",
            "depth_topic": "/warehouse/front/rgbd/depth_image",
            "imu_topic": "/warehouse/imu",
            "lidar_topic": "/warehouse/mid360/points",
            "rgb_depth_imu_ok": True,
            "lidar_ok": None,
            "sensors_ok": True,
            "tf_ok": True,
            "slam_ready": True,
        }
    )

    assert components["sensors_ok"] is True
    assert components["raw_lidar_healthy"] is None


def test_rgbd_visualization_probe_topics_prefers_warehouse_points() -> None:
    from backend.modules.warehouse.service.live_map_readiness import (
        _rgbd_visualization_probe_topics,
    )

    topics = {
        "/warehouse/front/rgbd/points",
        "/warehouse/drone/odometry",
        "/nvblox_node/combined_esdf_pointcloud",
    }
    probed = _rgbd_visualization_probe_topics(topics)
    assert probed[0] == "/warehouse/front/rgbd/points"
    assert "/nvblox_node/combined_esdf_pointcloud" not in probed


def test_mapping_readiness_flags_split_rgbd_inputs_and_pointcloud() -> None:
    from backend.modules.warehouse.service.live_map_readiness import (
        MappingReadinessResult,
        TopicTypeProbe,
    )

    result = MappingReadinessResult(
        ready=True,
        rgbd_input_topics_ready=True,
        rgbd_pointcloud_topic="/warehouse/front/rgbd/points",
        topic_probes=[
            TopicTypeProbe(
                topic="/warehouse/front/rgbd/points",
                present=False,
                bridge_kind="missing",
                info="not bridged yet",
            ),
            TopicTypeProbe(
                topic="/nvblox_node/static_esdf_pointcloud",
                present=True,
                message_type="sensor_msgs/msg/PointCloud2",
                bridge_kind="pointcloud2",
                ok_for_pointcloud_bridge=True,
            ),
        ],
    )
    flags = result.readiness_flags()
    assert flags["rgbd_input_ready"] is True
    assert flags["rgbd_colored_pointcloud_ready"] is False
    assert flags["nvblox_esdf_ready"] is True
    assert result.to_dict()["readiness_flags"] == flags


def test_readiness_accepts_warehouse_odometry_topic() -> None:
    status = SimpleNamespace(
        reachable=True,
        detail=None,
        components={
            "listed_topics": ["/warehouse/drone/odometry"],
            "odometry_topic": "/warehouse/drone/odometry",
        },
    )

    readiness = readiness_from_perception_status_strict(status)

    assert readiness.can_localize is True
    assert readiness.bridge_alive is True
    assert readiness.ros_graph_ready is True
    assert readiness.missing_required_topics == []


def test_readiness_ros_graph_ready_without_bridge_http() -> None:
    status = SimpleNamespace(
        reachable=False,
        detail="Bridge health unreachable",
        components={
            "listed_topics": ["/warehouse/drone/odometry", "/warehouse/imu"],
            "odometry_topic": "/warehouse/drone/odometry",
            "ros_graph_healthy": True,
        },
    )

    readiness = readiness_from_perception_status_strict(status)

    assert readiness.bridge_alive is True
    assert readiness.ros_graph_ready is True
    assert readiness.can_localize is True
    assert readiness.missing_required_topics == []


def test_readiness_accepts_nvblox_back_projected_depth_output() -> None:
    back_topic = (
        "/nvblox_node/back_projected_depth/"
        "iris_rplidar_rgbd/front_rgbd_camera_link/front_rgbd_camera"
    )
    status = SimpleNamespace(
        reachable=True,
        detail=None,
        components={
            "listed_topics": [
                "/warehouse/drone/odometry",
                back_topic,
            ],
            "odometry_topic": "/warehouse/drone/odometry",
        },
    )

    readiness = readiness_from_perception_status_strict(status)

    assert readiness.nvblox_ready is True
    assert readiness.ready is True
    assert readiness.missing_nvblox_topics == []


def test_rgbd_readiness_promotes_nvblox_gate_when_perception_probe_lags() -> None:
    from backend.modules.warehouse.service.live_map_readiness import (
        MappingReadinessResult,
    )
    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        _merge_nvblox_readiness_from_rgbd,
    )
    from backend.modules.warehouse.service.readiness_result import (
        WarehouseReadinessResult,
    )

    flight_readiness = WarehouseReadinessResult(
        bridge_alive=True,
        ros_graph_ready=True,
        can_localize=True,
        nvblox_ready=False,
        core_ready=True,
        bridge_reachable=True,
        ready=False,
        detail="Nvblox is not publishing a ready ESDF/costmap signal.",
        missing_required_topics=[],
        missing_nvblox_topics=["/nvblox_node/static_esdf_pointcloud"],
        unhealthy_topics=[],
    )
    rgbd_readiness = MappingReadinessResult(
        ready=True,
        rgbd_pointcloud_topic="/warehouse/front/rgbd/points",
        nvblox_pointcloud_topics=[
            "/nvblox_node/back_projected_depth/"
            "iris_rplidar_rgbd/front_rgbd_camera_link/front_rgbd_camera"
        ],
    )

    merged = _merge_nvblox_readiness_from_rgbd(flight_readiness, rgbd_readiness)

    assert merged.nvblox_ready is True
    assert merged.ready is True
    assert merged.missing_nvblox_topics == []


@pytest.mark.asyncio
async def test_mapping_stack_status_includes_log_parser_health(monkeypatch) -> None:
    from backend.modules.warehouse.service import (
        live_map_bridge,
        mapping_stack_lifecycle,
        warehouse_preflight,
    )

    async def _fake_status(*, deep: bool, force: bool):
        return SimpleNamespace(
            reachable=True,
            configured=True,
            detail=None,
            components={
                "listed_topics": ["/warehouse/drone/odometry"],
                "odometry_topic": "/warehouse/drone/odometry",
                "nvblox_healthy": False,
            },
        )

    monkeypatch.setattr(warehouse_preflight, "fetch_warehouse_perception_status", _fake_status)
    monkeypatch.setattr(live_map_bridge, "live_map_bridge_status", lambda: {"running": False})
    monkeypatch.setattr(mapping_stack_lifecycle, "_mapping_stack_process", None)

    status = await mapping_stack_lifecycle.get_mapping_stack_status()

    assert status.running is True
    assert status.nvblox_health["log_parser"]["available"] is True


@pytest.mark.asyncio
async def test_mapping_stack_status_endpoint_returns_warning(monkeypatch) -> None:
    from backend.modules.warehouse.routers import operations as api
    from backend.modules.warehouse.service import mapping_stack_lifecycle

    async def _fake_stack_status():
        return mapping_stack_lifecycle.WarehouseMappingStackStatus(
            running=True,
            nvblox_health={
                "log_parser": {
                    "available": False,
                    "warning": "parser unavailable",
                },
            },
        )

    monkeypatch.setattr(mapping_stack_lifecycle, "get_mapping_stack_status", _fake_stack_status)

    status = await api.mapping_stack_status(_org_user=object())

    assert status.running is True
    assert status.warning == "parser unavailable"


@pytest.mark.asyncio
async def test_mapping_stack_start_endpoint_uses_lifecycle_launcher(monkeypatch) -> None:
    from backend.modules.warehouse.routers import operations as api
    from backend.modules.warehouse.service import mapping_stack_lifecycle

    async def _fake_start_stack():
        return mapping_stack_lifecycle.WarehouseMappingStackStatus(
            running=True,
            pid=1234,
            nvblox_running=False,
            phase="starting",
        )

    monkeypatch.setattr(mapping_stack_lifecycle, "start_warehouse_mapping_stack", _fake_start_stack)

    status = await api.mapping_stack_start(_org_user=object())

    assert status.running is True
    assert status.pid == 1234
    assert status.phase == "starting"


def test_preflight_refresh_returns_running_job_without_blocking(monkeypatch) -> None:
    from backend.modules.warehouse.routers import preflight as api
    scheduled = {}

    def _schedule(**kwargs):
        scheduled.update(kwargs)

    monkeypatch.setattr(api, "schedule_preflight_refresh", _schedule)

    result = asyncio.run(
        api.refresh_preflight(
            org_user=SimpleNamespace(user=object()),
        )
    )

    assert result.status == "running"
    assert result.finished_at is None
    assert result.snapshot is None
    assert scheduled["run_id"] == result.run_id


@pytest.mark.asyncio
async def test_mapping_tf_probe_uses_current_ros_env_signature(monkeypatch) -> None:
    from backend.modules.warehouse.service import live_map_readiness

    calls: list[dict[str, object]] = []

    def _fake_ros_env() -> dict[str, str]:
        return {"ROS_DOMAIN_ID": "0"}

    async def _fake_to_thread(func, *args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(returncode=0, stdout="At time 1.0", stderr="")

    monkeypatch.setattr(live_map_readiness, "ros_command_env", _fake_ros_env)
    monkeypatch.setattr(live_map_readiness.asyncio, "to_thread", _fake_to_thread)

    result = await probe_mapping_tf_degraded()

    assert result["tf_ok"] is True
    assert calls[0]["env"] == {"ROS_DOMAIN_ID": "0"}


@pytest.mark.asyncio
async def test_shutdown_mapping_stack_is_best_effort_without_optional_tf_helper(
    monkeypatch,
) -> None:
    from backend.modules.warehouse.service import live_map_bridge, mapping_stack_lifecycle

    async def _stop_bridge() -> None:
        return None

    monkeypatch.setattr(live_map_bridge, "stop_warehouse_live_map_bridge", _stop_bridge)
    monkeypatch.setattr(mapping_stack_lifecycle, "_mapping_stack_process", None)
    monkeypatch.setattr(
        mapping_stack_lifecycle.settings,
        "warehouse_shutdown_mapping_stack_cmd",
        "",
    )

    await mapping_stack_lifecycle.shutdown_warehouse_mapping_stack()


@pytest.mark.asyncio
async def test_mapping_stack_status_survives_probe_failure(monkeypatch) -> None:
    from backend.modules.warehouse.service import mapping_stack_lifecycle

    async def _boom():
        raise RuntimeError("perception probe unavailable")

    monkeypatch.setattr(
        mapping_stack_lifecycle,
        "_get_mapping_stack_status_impl",
        _boom,
    )
    monkeypatch.setattr(mapping_stack_lifecycle, "_mapping_stack_process", None)

    status = await mapping_stack_lifecycle.get_mapping_stack_status()

    assert status.phase == "degraded"
    assert status.last_error == "perception probe unavailable"
    assert status.nvblox_health["log_parser"]["available"] is True


@pytest.mark.asyncio
async def test_structure_readiness_selects_valid_static_esdf_and_combined_occupancy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.modules.warehouse.service import live_map_readiness as readiness

    topics = {
        "/nvblox_node/static_esdf_pointcloud",
        "/nvblox_node/combined_occupancy_grid",
    }
    esdf_yaml = (
        "header:\n  frame_id: odom\n"
        "fields:\n- name: x\n- name: y\n- name: z\n- name: intensity"
    )
    occupancy_yaml = (
        "header:\n  frame_id: odom\n"
        "info:\n  width: 2\n  height: 2\n  resolution: 1.0\n"
        "  origin:\n    position:\n      x: 0.0\n      y: 0.0\n"
        "data: [0, 0, 100, 0]"
    )
    monkeypatch.setattr(readiness, "list_ros2_topics", lambda _ws: sorted(topics))
    monkeypatch.setattr(
        readiness,
        "_topic_info",
        lambda topic, _ws: (
            "sensor_msgs/msg/PointCloud2" if "esdf" in topic else "nav_msgs/msg/OccupancyGrid"
        ),
    )
    monkeypatch.setattr(
        readiness,
        "_topic_message_text",
        lambda topic, _ws, timeout_s: esdf_yaml if "esdf" in topic else occupancy_yaml,
    )

    result = await readiness.refresh_structure_input_readiness(timeout_s=1.0)

    assert result.esdf_available is True
    assert result.esdf_topic == "/nvblox_node/static_esdf_pointcloud"
    assert result.occupancy_available is True
    assert result.occupancy_topic == "/nvblox_node/combined_occupancy_grid"


@pytest.mark.asyncio
async def test_structure_readiness_uses_esdf_and_occupancy_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.modules.warehouse.service import live_map_readiness as readiness

    topics = {
        "/nvblox_node/pessimistic_static_esdf_pointcloud",
        "/nvblox_node/static_occupancy_grid",
    }
    monkeypatch.setattr(readiness, "list_ros2_topics", lambda _ws: sorted(topics))
    monkeypatch.setattr(
        readiness,
        "_topic_info",
        lambda topic, _ws: (
            "sensor_msgs/msg/PointCloud2" if "esdf" in topic else "nav_msgs/msg/OccupancyGrid"
        ),
    )
    monkeypatch.setattr(
        readiness,
        "_topic_message_text",
        lambda topic, _ws, timeout_s: (
            "header:\n  frame_id: odom\nfields:\n- name: x\n- name: y\n- name: z"
            if "esdf" in topic
            else "header:\n  frame_id: odom\ninfo:\n  width: 1\n  height: 1\ndata: [0]"
        ),
    )

    result = await readiness.refresh_structure_input_readiness(timeout_s=1.0)

    assert result.esdf_topic == "/nvblox_node/pessimistic_static_esdf_pointcloud"
    assert result.occupancy_topic == "/nvblox_node/static_occupancy_grid"
