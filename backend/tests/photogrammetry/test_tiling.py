from __future__ import annotations

import math

from backend.services.photogrammetry.tiling import _region_from_bbox


def test_region_from_direct_bbox_keys() -> None:
    region = _region_from_bbox(
        {
            "west": -122.05576875,
            "south": 37.98546614,
            "east": -122.05476149,
            "north": 37.98619849,
        }
    )

    assert region is not None
    assert region[0] == math.radians(-122.05576875)
    assert region[1] == math.radians(37.98546614)
    assert region[2] == math.radians(-122.05476149)
    assert region[3] == math.radians(37.98619849)
