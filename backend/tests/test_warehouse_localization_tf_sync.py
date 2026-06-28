from backend.modules.warehouse.service.localization_tf_sync import transform_stamped_yaml


def test_transform_stamped_yaml_uses_warehouse_map_frames() -> None:
    yaml_text = transform_stamped_yaml(
        {
            "translation": {"x": 1.5, "y": -2.0, "z": 0.25},
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.7071068, "w": 0.7071068},
        }
    )
    assert "frame_id: warehouse_map" in yaml_text
    assert "child_frame_id: odom" in yaml_text
    assert "x: 1.5" in yaml_text
    assert "y: -2.0" in yaml_text
