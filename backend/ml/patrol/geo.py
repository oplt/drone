from __future__ import annotations

import math

from backend.ml.patrol.models import GeoPoint


class GeoProjector:
    """Approximate flat-ground projection from image coordinates to GPS.

    This is not a calibrated photogrammetry model. It assumes:
    - a flat ground plane
    - a camera footprint derived from nominal FOV values
    - heading aligned with the camera forward direction

    It is still materially better than pinning every detection to the drone GPS
    because zone checks can now distinguish image-left/image-right objects.
    """

    DEFAULT_IMAGE_WIDTH_PX = 1920
    DEFAULT_IMAGE_HEIGHT_PX = 1080
    DEFAULT_CAMERA_FOV_H_DEG = 78.0
    DEFAULT_CAMERA_FOV_V_DEG = 62.0

    def __init__(
        self,
        *,
        camera_fov_h_deg: float = DEFAULT_CAMERA_FOV_H_DEG,
        camera_fov_v_deg: float = DEFAULT_CAMERA_FOV_V_DEG,
    ) -> None:
        self.camera_fov_h_deg = float(camera_fov_h_deg)
        self.camera_fov_v_deg = float(camera_fov_v_deg)

    def estimate_ground_point(
        self,
        *,
        centroid_px: tuple[int, int],
        drone_lat: float,
        drone_lon: float,
        altitude_m: float,
        gimbal_pitch_deg: float,
        heading_deg: float = 0.0,
        image_shape: tuple[int, ...] | None = None,
    ) -> GeoPoint:
        if image_shape and len(image_shape) >= 2:
            image_height_px = max(1, int(image_shape[0]))
            image_width_px = max(1, int(image_shape[1]))
        else:
            image_width_px = self.DEFAULT_IMAGE_WIDTH_PX
            image_height_px = self.DEFAULT_IMAGE_HEIGHT_PX

        cx, cy = centroid_px
        normalized_x = ((float(cx) + 0.5) / float(image_width_px)) - 0.5
        normalized_y = 0.5 - ((float(cy) + 0.5) / float(image_height_px))

        footprint_width_m = 2.0 * float(altitude_m) * math.tan(
            math.radians(self.camera_fov_h_deg / 2.0)
        )
        footprint_height_m = 2.0 * float(altitude_m) * math.tan(
            math.radians(self.camera_fov_v_deg / 2.0)
        )

        right_m = normalized_x * footprint_width_m
        forward_m = normalized_y * footprint_height_m

        pitch_abs_deg = abs(float(gimbal_pitch_deg))
        if 10.0 <= pitch_abs_deg < 89.5:
            # A camera tilted toward the horizon sees the image center ahead of the drone.
            forward_m += float(altitude_m) / math.tan(math.radians(pitch_abs_deg))

        heading_rad = math.radians(float(heading_deg) % 360.0)
        north_m = (forward_m * math.cos(heading_rad)) - (right_m * math.sin(heading_rad))
        east_m = (forward_m * math.sin(heading_rad)) + (right_m * math.cos(heading_rad))

        meters_per_deg_lat = 111_320.0
        meters_per_deg_lon = max(
            1.0,
            meters_per_deg_lat * math.cos(math.radians(float(drone_lat))),
        )

        projected_lat = float(drone_lat) + (north_m / meters_per_deg_lat)
        projected_lon = float(drone_lon) + (east_m / meters_per_deg_lon)
        return GeoPoint(lat=projected_lat, lon=projected_lon, alt=0.0)
