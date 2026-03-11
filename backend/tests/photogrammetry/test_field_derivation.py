from __future__ import annotations

import pytest

from backend.services.photogrammetry.field_derivation import (
    derive_field_ring_from_bbox_wgs84,
    derive_field_ring_from_points,
    gps_decimal_from_exif_ifd,
    ring_to_polygon_wkt,
)


def test_gps_decimal_from_exif_ifd_converts_dms_to_lon_lat() -> None:
    gps_ifd = {
        1: "N",
        2: (37.0, 59.0, 9.3995),
        3: "W",
        4: (122.0, 3.0, 19.2721),
    }

    point = gps_decimal_from_exif_ifd(gps_ifd)

    assert point is not None
    lon, lat = point
    assert lon == pytest.approx(-122.055353, abs=1e-6)
    assert lat == pytest.approx(37.985944, abs=1e-6)


def test_derive_field_ring_from_points_expands_small_extents() -> None:
    ring = derive_field_ring_from_points([(4.3517, 50.8503)])

    assert ring is not None
    assert len(ring) == 4
    west, south = ring[0]
    east, north = ring[2]
    assert west < 4.3517 < east
    assert south < 50.8503 < north


def test_derive_field_ring_from_bbox_wgs84_reads_geojson_extent() -> None:
    bbox_wgs84 = {
        "type": "Polygon",
        "coordinates": [
            [
                [4.0, 50.0],
                [5.0, 50.0],
                [5.0, 51.0],
                [4.0, 51.0],
                [4.0, 50.0],
            ]
        ],
    }

    ring = derive_field_ring_from_bbox_wgs84(bbox_wgs84)

    assert ring == [[4.0, 50.0], [5.0, 50.0], [5.0, 51.0], [4.0, 51.0]]


def test_ring_to_polygon_wkt_closes_the_ring() -> None:
    wkt = ring_to_polygon_wkt([[4.0, 50.0], [5.0, 50.0], [5.0, 51.0], [4.0, 51.0]])

    assert wkt == "POLYGON((4.0 50.0, 5.0 50.0, 5.0 51.0, 4.0 51.0, 4.0 50.0))"
