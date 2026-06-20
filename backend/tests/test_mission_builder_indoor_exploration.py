from backend.modules.missions.schemas.mission_create import MissionCreateIn
from backend.modules.missions.service.mission_builder import build_mission


def test_indoor_exploration_builds_existing_planner() -> None:
    payload = MissionCreateIn.model_validate(
        {
            "name": "Explore aisle",
            "mission_type": "indoor_exploration",
            "cruise_alt": 2.5,
            "warehouse_scan": {
                "dock_config": {
                    "dock_pose": {"x_m": 0, "y_m": 0, "z_m": 0},
                    "entry_pose": {"x_m": 1, "y_m": 0, "z_m": 2.5},
                    "exit_pose": {"x_m": 2, "y_m": 0, "z_m": 2.5},
                }
            },
        }
    )

    mission, waypoint_count = build_mission(payload, owner_id=7)

    assert mission.mission_type == "indoor_exploration"
    assert mission.owner_id == 7
    assert waypoint_count == 0
