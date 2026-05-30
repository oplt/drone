from __future__ import annotations

import asyncio
from types import SimpleNamespace

from backend.modules.missions.schemas.mission_types import (
    WarehouseLocalPoint,
    WarehouseScanLayer,
    WarehouseScanMission,
)
from backend.modules.preflight.checks.context import PreflightContext
from backend.modules.preflight.checks.mission_specific import WarehouseScanMissionPreflight


def _mission(sensor_rig_id: int | None = 9) -> WarehouseScanMission:
    return WarehouseScanMission(
        type="warehouse_scan",
        sensor_rig_id=sensor_rig_id,
        local_polygon=[
            WarehouseLocalPoint(x_m=0.0, y_m=0.0),
            WarehouseLocalPoint(x_m=10.0, y_m=0.0),
            WarehouseLocalPoint(x_m=10.0, y_m=10.0),
        ],
        scan_layers=[WarehouseScanLayer(layer_index=0, label="L0", z_m=2.0)],
    )


def _components(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ros_graph": True,
        "camera_topics": True,
        "stereo_sync": True,
        "imu_topic": True,
        "tf_tree": True,
        "visual_slam": True,
        "nvblox": True,
        "disk_free_gb": 25.0,
    }
    base.update(overrides)
    return base


def _checker(
    *,
    components: dict[str, object] | None = None,
    sensor_rig_id: int | None = 9,
    bridge_ready: bool = True,
) -> WarehouseScanMissionPreflight:
    ctx = PreflightContext(
        vehicle_state=SimpleNamespace(
            local_position_ok=True,
            battery_percent=0.82,
            odometry_healthy=True,
            lidar_healthy=True,
        ),
        mission=_mission(sensor_rig_id=sensor_rig_id),
        config_overrides={
            "WAREHOUSE_PERCEPTION_STATUS": {
                "configured": True,
                "reachable": True,
                "ready": bridge_ready,
                "status": "ready" if bridge_ready else "degraded",
                "profile": "isaac_ros_nvblox_stereo",
                "components": components if components is not None else _components(),
            }
        },
    )
    return WarehouseScanMissionPreflight(ctx)


def test_warehouse_ros_preflight_passes_when_isaac_stack_ready() -> None:
    results = asyncio.run(_checker().run())

    by_name = {result.name: result.status for result in results}

    assert by_name["Warehouse ROS Bridge"] == "PASS"
    assert by_name["Warehouse Camera Topics"] == "PASS"
    assert by_name["Warehouse Stereo Sync"] == "PASS"
    assert by_name["Warehouse TF Tree"] == "PASS"
    assert by_name["Warehouse Visual SLAM"] == "PASS"
    assert by_name["Warehouse Nvblox"] == "PASS"
    assert by_name["Warehouse Mapping Disk"] == "PASS"
    assert by_name["Warehouse Sensor Rig"] == "PASS"
    assert by_name["Warehouse Battery Margin"] == "PASS"


def test_warehouse_ros_preflight_fails_for_missing_runtime_signals() -> None:
    results = asyncio.run(
        _checker(
            components=_components(
                camera_topics=False,
                stereo_sync=False,
                tf_tree=False,
                disk_free_gb=2.0,
            ),
            sensor_rig_id=None,
        ).run()
    )

    by_name = {result.name: result.status for result in results}

    assert by_name["Warehouse Camera Topics"] == "FAIL"
    assert by_name["Warehouse Stereo Sync"] == "FAIL"
    assert by_name["Warehouse TF Tree"] == "FAIL"
    assert by_name["Warehouse Mapping Disk"] == "FAIL"
    assert by_name["Warehouse Sensor Rig"] == "FAIL"
