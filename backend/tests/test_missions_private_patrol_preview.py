from backend.modules.missions.api.mission_route_schemas import PrivatePatrolPreviewIn
from backend.modules.missions.service.private_patrol_preview import build_private_patrol_preview


def test_private_patrol_preview_normalizes_perimeter_status_fields() -> None:
    preview = build_private_patrol_preview(
        PrivatePatrolPreviewIn.model_validate(
            {
                "task_type": "perimeter_patrol",
                "property_polygon_lonlat": [
                    [4.35, 50.85],
                    [4.36, 50.85],
                    [4.36, 50.86],
                    [4.35, 50.86],
                ],
                "patrol_loops": 1,
                "speed_mps": 6.0,
            }
        )
    )

    assert preview.waypoints
    assert preview.stats["task_type"] == "perimeter_patrol"
    assert preview.stats["waypoints"] == len(preview.waypoints)
    assert len(preview.work_leg_mask) == max(0, len(preview.waypoints) - 1)
    assert preview.ai_tasks
