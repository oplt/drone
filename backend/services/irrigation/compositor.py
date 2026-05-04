from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.services.irrigation.geometry import (
    GeoBounds,
    latlon_to_local_xy,
    local_xy_to_latlon,
    polygon_bbox,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptureFootprint:
    capture_id: int
    image_uri: str
    local_bounds_m: tuple[float, float, float, float]
    geo_polygon: list[tuple[float, float]]
    pixel_rect: tuple[int, int, int, int]


@dataclass(frozen=True)
class CompositeResult:
    preview_path: Path
    preview_width: int
    preview_height: int
    resolution_m_per_px: float
    bounds: GeoBounds
    footprints: list[CaptureFootprint]


def _safe_altitude(alt_m: float | None) -> float:
    if alt_m is None or not math.isfinite(alt_m):
        return 30.0
    return max(8.0, min(float(alt_m), 120.0))


def _footprint_size_m(*, alt_m: float | None, fov_h_deg: float, fov_v_deg: float) -> tuple[float, float]:
    altitude = _safe_altitude(alt_m)
    width_m = 2.0 * altitude * math.tan(math.radians(fov_h_deg / 2.0))
    height_m = 2.0 * altitude * math.tan(math.radians(fov_v_deg / 2.0))
    return max(6.0, width_m), max(6.0, height_m)


def build_field_composite(
    *,
    captures: list[Any],
    output_dir: Path,
    fov_h_deg: float = 78.0,
    fov_v_deg: float = 62.0,
    max_canvas_px: int = 1600,
) -> CompositeResult:
    if not captures:
        raise ValueError("At least one capture is required to build a field composite.")

    output_dir.mkdir(parents=True, exist_ok=True)
    origin_lat = float(sum(float(c.lat) for c in captures) / len(captures))
    origin_lon = float(sum(float(c.lon) for c in captures) / len(captures))

    footprint_specs: list[dict[str, Any]] = []
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for capture in captures:
        center_x, center_y = latlon_to_local_xy(
            lat=float(capture.lat),
            lon=float(capture.lon),
            origin_lat=origin_lat,
            origin_lon=origin_lon,
        )
        width_m, height_m = _footprint_size_m(
            alt_m=getattr(capture, "alt_m", None),
            fov_h_deg=fov_h_deg,
            fov_v_deg=fov_v_deg,
        )
        half_w = width_m / 2.0
        half_h = height_m / 2.0
        bounds_m = (
            center_x - half_w,
            center_y - half_h,
            center_x + half_w,
            center_y + half_h,
        )
        min_x = min(min_x, bounds_m[0])
        min_y = min(min_y, bounds_m[1])
        max_x = max(max_x, bounds_m[2])
        max_y = max(max_y, bounds_m[3])
        footprint_specs.append(
            {
                "capture": capture,
                "center_x": center_x,
                "center_y": center_y,
                "width_m": width_m,
                "height_m": height_m,
                "bounds_m": bounds_m,
            }
        )

    span_x = max(1.0, max_x - min_x)
    span_y = max(1.0, max_y - min_y)
    resolution_m_per_px = max(span_x, span_y) / float(max_canvas_px)
    resolution_m_per_px = max(0.03, resolution_m_per_px)
    canvas_width = int(math.ceil(span_x / resolution_m_per_px)) + 8
    canvas_height = int(math.ceil(span_y / resolution_m_per_px)) + 8
    canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.float32)
    weights = np.zeros((canvas_height, canvas_width, 1), dtype=np.float32)
    footprints: list[CaptureFootprint] = []

    for spec in footprint_specs:
        capture = spec["capture"]
        image_path = Path(str(capture.image_uri))
        if str(capture.image_uri).startswith("/irrigation-assets/"):
            continue
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            logger.warning("Skipping unreadable irrigation capture image: %s", image_path)
            continue

        dest_w = max(4, int(round(spec["width_m"] / resolution_m_per_px)))
        dest_h = max(4, int(round(spec["height_m"] / resolution_m_per_px)))
        resized = cv2.resize(image, (dest_w, dest_h), interpolation=cv2.INTER_AREA)
        left = int(round((spec["bounds_m"][0] - min_x) / resolution_m_per_px))
        top = int(round((max_y - spec["bounds_m"][3]) / resolution_m_per_px))
        right = min(canvas_width, left + dest_w)
        bottom = min(canvas_height, top + dest_h)
        if right <= 0 or bottom <= 0 or left >= canvas_width or top >= canvas_height:
            continue
        clip_left = max(0, left)
        clip_top = max(0, top)
        src_left = clip_left - left
        src_top = clip_top - top
        src_right = src_left + (right - clip_left)
        src_bottom = src_top + (bottom - clip_top)
        tile = resized[src_top:src_bottom, src_left:src_right].astype(np.float32)
        if tile.size == 0:
            continue
        mask = np.any(tile > 0, axis=2, keepdims=True).astype(np.float32)
        canvas[clip_top:bottom, clip_left:right] += tile * mask
        weights[clip_top:bottom, clip_left:right] += mask

        geo_polygon = [
            local_xy_to_latlon(x_m=spec["bounds_m"][0], y_m=spec["bounds_m"][1], origin_lat=origin_lat, origin_lon=origin_lon),
            local_xy_to_latlon(x_m=spec["bounds_m"][2], y_m=spec["bounds_m"][1], origin_lat=origin_lat, origin_lon=origin_lon),
            local_xy_to_latlon(x_m=spec["bounds_m"][2], y_m=spec["bounds_m"][3], origin_lat=origin_lat, origin_lon=origin_lon),
            local_xy_to_latlon(x_m=spec["bounds_m"][0], y_m=spec["bounds_m"][3], origin_lat=origin_lat, origin_lon=origin_lon),
            local_xy_to_latlon(x_m=spec["bounds_m"][0], y_m=spec["bounds_m"][1], origin_lat=origin_lat, origin_lon=origin_lon),
        ]
        footprints.append(
            CaptureFootprint(
                capture_id=int(capture.id),
                image_uri=str(capture.image_uri),
                local_bounds_m=spec["bounds_m"],
                geo_polygon=geo_polygon,
                pixel_rect=(clip_left, clip_top, right, bottom),
            )
        )

    weights_safe = np.maximum(weights, 1.0)
    blended = np.clip(canvas / weights_safe, 0, 255).astype(np.uint8)
    preview_path = output_dir / "stitched_preview.png"
    cv2.imwrite(str(preview_path), blended)

    preview_bounds = polygon_bbox(
        [
            local_xy_to_latlon(x_m=min_x, y_m=min_y, origin_lat=origin_lat, origin_lon=origin_lon),
            local_xy_to_latlon(x_m=max_x, y_m=max_y, origin_lat=origin_lat, origin_lon=origin_lon),
        ]
    )
    return CompositeResult(
        preview_path=preview_path,
        preview_width=canvas_width,
        preview_height=canvas_height,
        resolution_m_per_px=resolution_m_per_px,
        bounds=preview_bounds,
        footprints=footprints,
    )
