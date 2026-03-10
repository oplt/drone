from __future__ import annotations

import unittest

from backend.ml.patrol.geo import GeoProjector


class GeoProjectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.projector = GeoProjector()

    def test_center_pixel_projects_near_drone_position(self) -> None:
        point = self.projector.estimate_ground_point(
            centroid_px=(959, 539),
            drone_lat=50.0,
            drone_lon=4.0,
            altitude_m=40.0,
            gimbal_pitch_deg=0.0,
            heading_deg=0.0,
            image_shape=(1080, 1920, 3),
        )

        self.assertAlmostEqual(point.lat, 50.0, places=5)
        self.assertAlmostEqual(point.lon, 4.0, places=5)

    def test_right_side_pixel_moves_projection_east_when_heading_north(self) -> None:
        center = self.projector.estimate_ground_point(
            centroid_px=(959, 539),
            drone_lat=50.0,
            drone_lon=4.0,
            altitude_m=40.0,
            gimbal_pitch_deg=0.0,
            heading_deg=0.0,
            image_shape=(1080, 1920, 3),
        )
        right = self.projector.estimate_ground_point(
            centroid_px=(1800, 539),
            drone_lat=50.0,
            drone_lon=4.0,
            altitude_m=40.0,
            gimbal_pitch_deg=0.0,
            heading_deg=0.0,
            image_shape=(1080, 1920, 3),
        )

        self.assertGreater(right.lon, center.lon)
        self.assertAlmostEqual(right.lat, center.lat, places=4)

    def test_top_pixel_moves_projection_forward_relative_to_heading(self) -> None:
        north_heading = self.projector.estimate_ground_point(
            centroid_px=(959, 50),
            drone_lat=50.0,
            drone_lon=4.0,
            altitude_m=40.0,
            gimbal_pitch_deg=0.0,
            heading_deg=0.0,
            image_shape=(1080, 1920, 3),
        )
        east_heading = self.projector.estimate_ground_point(
            centroid_px=(959, 50),
            drone_lat=50.0,
            drone_lon=4.0,
            altitude_m=40.0,
            gimbal_pitch_deg=0.0,
            heading_deg=90.0,
            image_shape=(1080, 1920, 3),
        )

        self.assertGreater(north_heading.lat, 50.0)
        self.assertGreater(east_heading.lon, 4.0)


if __name__ == "__main__":
    unittest.main()
