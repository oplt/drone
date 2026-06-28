import numpy as np
import pytest
from pydantic import ValidationError

from backend.modules.warehouse.models import WarehouseAsset, WarehouseModel
from backend.modules.warehouse.routers.coordinate_frames import CoordinateFrameCreate
from backend.modules.warehouse.service.coordinate_frames import (
    transform_odom_points,
    transform_warehouse_points,
    validate_transform,
)


def test_transform_odom_points_applies_translation_and_rotation() -> None:
    # +90 degrees around Z, then translate.
    transform = {
        "translation": {"x": 10.0, "y": 20.0, "z": 1.0},
        "rotation": {"x": 0.0, "y": 0.0, "z": 2**-0.5, "w": 2**-0.5},
    }
    result = transform_odom_points(np.array([[1.0, 0.0, 2.0]]), transform)
    np.testing.assert_allclose(result, [[10.0, 21.0, 3.0]], atol=1e-6)
    np.testing.assert_allclose(
        transform_warehouse_points(result, transform), [[1.0, 0.0, 2.0]], atol=1e-6
    )


def test_transform_rejects_non_unit_quaternion() -> None:
    with pytest.raises(ValueError, match="normalized"):
        validate_transform(
            {
                "translation": {"x": 0, "y": 0, "z": 0},
                "rotation": {"x": 0, "y": 0, "z": 0, "w": 2},
            }
        )


def test_coordinate_contract_rejects_partial_covariance() -> None:
    with pytest.raises(ValidationError, match="row-major 6x6"):
        CoordinateFrameCreate.model_validate(
            {
                "transform": {
                    "translation": {"x": 0, "y": 0, "z": 0},
                    "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                },
                "source": "fiducial_localization",
                "confidence": 0.95,
                "covariance": [0.1],
            }
        )


def test_models_and_assets_have_queryable_coordinate_provenance() -> None:
    assert "coordinate_frame_id" in WarehouseModel.__table__.columns
    assert "coordinate_frame_id" in WarehouseAsset.__table__.columns
    assert "frame_id" in WarehouseAsset.__table__.columns
