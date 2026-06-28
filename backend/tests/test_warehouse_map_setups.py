import pytest
from pydantic import ValidationError
from sqlalchemy.orm import configure_mappers

from backend.modules.warehouse.models import WarehouseMapSetupVersion
from backend.modules.warehouse.routers.map_setups import MapSetupCreate

IDENTITY = {
    "translation": {"x": 1.0, "y": 2.0, "z": 0.0},
    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
}


def test_arbitrary_polygon_setup_contract() -> None:
    setup = MapSetupCreate.model_validate(
        {
            "polygon_local_m": [[0, 0], [8, 1], [7, 5], [2, 7], [-1, 3]],
            "origin_transform": IDENTITY,
            "alignment_deg": 12.5,
            "alignment_reference": "aisle",
        }
    )

    assert len(setup.polygon_local_m) == 5
    assert setup.origin_transform["translation"]["x"] == 1.0


def test_invalid_polygon_and_origin_are_rejected() -> None:
    with pytest.raises(ValidationError):
        MapSetupCreate.model_validate(
            {
                "polygon_local_m": [[0, 0], [1, 1], [2, 2]],
                "origin_transform": IDENTITY,
            }
        )
    with pytest.raises(ValidationError, match="normalized"):
        MapSetupCreate.model_validate(
            {
                "polygon_local_m": [[0, 0], [2, 0], [0, 2]],
                "origin_transform": {
                    **IDENTITY,
                    "rotation": {"x": 0, "y": 0, "z": 0, "w": 2},
                },
            }
        )


def test_setup_model_has_version_and_lock_provenance() -> None:
    configure_mappers()
    columns = WarehouseMapSetupVersion.__table__.columns

    assert "coordinate_frame_id" in columns
    assert "polygon_local_json" in columns
    assert "origin_transform_json" in columns
    assert "locked_at" in columns
