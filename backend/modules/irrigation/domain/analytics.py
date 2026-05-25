from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.modules.irrigation.domain.geometry import clamp01, local_xy_to_latlon, polygon_area_m2


@dataclass(frozen=True)
class GridIndex:
    row0: int
    col0: int
    row1: int
    col1: int


def _zscore(values: np.ndarray) -> np.ndarray:
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std < 1e-6:
        return np.zeros_like(values)
    return (values - mean) / std


def _cluster_mask(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    clusters: list[list[tuple[int, int]]] = []
    visited = np.zeros_like(mask, dtype=bool)
    rows, cols = mask.shape
    for row in range(rows):
        for col in range(cols):
            if visited[row, col] or not mask[row, col]:
                continue
            queue = [(row, col)]
            visited[row, col] = True
            cluster: list[tuple[int, int]] = []
            while queue:
                current_row, current_col = queue.pop()
                cluster.append((current_row, current_col))
                for delta_row, delta_col in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    next_row = current_row + delta_row
                    next_col = current_col + delta_col
                    if (
                        0 <= next_row < rows
                        and 0 <= next_col < cols
                        and not visited[next_row, next_col]
                        and mask[next_row, next_col]
                    ):
                        visited[next_row, next_col] = True
                        queue.append((next_row, next_col))
            clusters.append(cluster)
    return clusters


def _bbox_polygon_for_cluster(
    *,
    cluster: list[tuple[int, int]],
    patch_size_px: int,
    resolution_m_per_px: float,
    canvas_height: int,
    min_x_m: float,
    max_y_m: float,
    origin_lat: float,
    origin_lon: float,
) -> tuple[list[tuple[float, float]], GridIndex]:
    min_row = min(row for row, _ in cluster)
    max_row = max(row for row, _ in cluster)
    min_col = min(col for _, col in cluster)
    max_col = max(col for _, col in cluster)
    left_px = min_col * patch_size_px
    right_px = (max_col + 1) * patch_size_px
    top_px = min_row * patch_size_px
    bottom_px = (max_row + 1) * patch_size_px
    min_local_x = min_x_m + (left_px * resolution_m_per_px)
    max_local_x = min_x_m + (right_px * resolution_m_per_px)
    max_local_y = max_y_m - (top_px * resolution_m_per_px)
    min_local_y = max_y_m - (bottom_px * resolution_m_per_px)
    polygon = [
        local_xy_to_latlon(
            x_m=min_local_x, y_m=min_local_y, origin_lat=origin_lat, origin_lon=origin_lon
        ),
        local_xy_to_latlon(
            x_m=max_local_x, y_m=min_local_y, origin_lat=origin_lat, origin_lon=origin_lon
        ),
        local_xy_to_latlon(
            x_m=max_local_x, y_m=max_local_y, origin_lat=origin_lat, origin_lon=origin_lon
        ),
        local_xy_to_latlon(
            x_m=min_local_x, y_m=max_local_y, origin_lat=origin_lat, origin_lon=origin_lon
        ),
        local_xy_to_latlon(
            x_m=min_local_x, y_m=min_local_y, origin_lat=origin_lat, origin_lon=origin_lon
        ),
    ]
    return polygon, GridIndex(top_px, left_px, bottom_px, right_px)


def analyze_irrigation(
    *,
    preview_path: Path,
    resolution_m_per_px: float,
    bounds: dict[str, float],
    capture_ids: list[int],
    patch_size_px: int = 64,
) -> dict[str, Any]:
    image = cv2.imread(str(preview_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Unable to read irrigation preview image: {preview_path}")

    canvas_height, canvas_width = image.shape[:2]
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    green_excess = np.clip((2.0 * rgb[:, :, 1]) - rgb[:, :, 0] - rgb[:, :, 2], -1.0, 1.0)
    brightness = np.mean(rgb, axis=2)
    saturation = np.max(rgb, axis=2) - np.min(rgb, axis=2)

    rows = max(1, math.ceil(canvas_height / patch_size_px))
    cols = max(1, math.ceil(canvas_width / patch_size_px))
    exg_grid = np.zeros((rows, cols), dtype=np.float32)
    brightness_grid = np.zeros((rows, cols), dtype=np.float32)
    saturation_grid = np.zeros((rows, cols), dtype=np.float32)
    valid_grid = np.zeros((rows, cols), dtype=bool)

    for row in range(rows):
        for col in range(cols):
            row_slice = slice(row * patch_size_px, min(canvas_height, (row + 1) * patch_size_px))
            col_slice = slice(col * patch_size_px, min(canvas_width, (col + 1) * patch_size_px))
            patch_brightness = brightness[row_slice, col_slice]
            patch_valid = patch_brightness > 0.02
            if np.count_nonzero(patch_valid) < 16:
                continue
            valid_grid[row, col] = True
            exg_grid[row, col] = float(np.mean(green_excess[row_slice, col_slice][patch_valid]))
            brightness_grid[row, col] = float(np.mean(patch_brightness[patch_valid]))
            saturation_grid[row, col] = float(
                np.mean(saturation[row_slice, col_slice][patch_valid])
            )

    valid_values = valid_grid.astype(bool)
    if not np.any(valid_values):
        return {"zones": [], "inspection_points": [], "summary": {"status": "failed"}}

    exg_z = np.zeros_like(exg_grid)
    bright_z = np.zeros_like(brightness_grid)
    sat_z = np.zeros_like(saturation_grid)
    exg_z[valid_values] = _zscore(exg_grid[valid_values])
    bright_z[valid_values] = _zscore(brightness_grid[valid_values])
    sat_z[valid_values] = _zscore(saturation_grid[valid_values])

    row_profile = np.zeros(rows, dtype=np.float32)
    col_profile = np.zeros(cols, dtype=np.float32)
    for row in range(rows):
        row_valid = valid_grid[row]
        if np.any(row_valid):
            row_profile[row] = float(np.mean(exg_grid[row][row_valid]))
    for col in range(cols):
        col_valid = valid_grid[:, col]
        if np.any(col_valid):
            col_profile[col] = float(np.mean(exg_grid[:, col][col_valid]))
    row_z = _zscore(row_profile)
    col_z = _zscore(col_profile)

    under_score = np.zeros_like(exg_grid)
    over_score = np.zeros_like(exg_grid)
    uneven_score = np.zeros_like(exg_grid)
    under_score[valid_values] = (
        np.maximum(-exg_z[valid_values], 0.0) + np.maximum(bright_z[valid_values], 0.0) * 0.35
    )
    over_score[valid_values] = (
        np.maximum(-bright_z[valid_values], 0.0) + np.maximum(-sat_z[valid_values], 0.0) * 0.25
    )
    for row in range(rows):
        for col in range(cols):
            if not valid_grid[row, col]:
                continue
            uneven_score[row, col] = (
                abs(float(row_z[row])) * 0.6
                + abs(float(col_z[col])) * 0.4
                + abs(float(exg_z[row, col])) * 0.25
            )

    thresholds = {
        "under_irrigated": max(0.8, float(np.quantile(under_score[valid_values], 0.82))),
        "overwatered": max(0.7, float(np.quantile(over_score[valid_values], 0.82))),
        "uneven_distribution": max(0.85, float(np.quantile(uneven_score[valid_values], 0.84))),
    }
    score_maps = {
        "under_irrigated": under_score,
        "overwatered": over_score,
        "uneven_distribution": uneven_score,
    }

    origin_lat = float(bounds["origin_lat"])
    origin_lon = float(bounds["origin_lon"])
    min_x_m = float(bounds["min_x_m"])
    max_y_m = float(bounds["max_y_m"])
    zones: list[dict[str, Any]] = []
    inspection_points: list[dict[str, Any]] = []

    for zone_type, score_map in score_maps.items():
        mask = (score_map >= thresholds[zone_type]) & valid_grid
        for cluster in _cluster_mask(mask):
            if len(cluster) < 2:
                continue
            polygon, patch_index = _bbox_polygon_for_cluster(
                cluster=cluster,
                patch_size_px=patch_size_px,
                resolution_m_per_px=resolution_m_per_px,
                canvas_height=canvas_height,
                min_x_m=min_x_m,
                max_y_m=max_y_m,
                origin_lat=origin_lat,
                origin_lon=origin_lon,
            )
            cluster_scores = [float(score_map[row, col]) for row, col in cluster]
            severity = clamp01((float(np.mean(cluster_scores)) - 0.5) / 1.6)
            span_rows = max(row for row, _ in cluster) - min(row for row, _ in cluster) + 1
            span_cols = max(col for _, col in cluster) - min(col for _, col in cluster) + 1
            elongation = max(span_rows, span_cols) / max(1, min(span_rows, span_cols))
            confidence = clamp01(0.45 + severity * 0.35 + min(0.2, len(cluster) / 40.0))
            if zone_type == "uneven_distribution":
                confidence = clamp01(confidence + min(0.15, (elongation - 1.0) * 0.08))
            centroid_lat = sum(lat for lat, _ in polygon[:-1]) / 4.0
            centroid_lon = sum(lon for _, lon in polygon[:-1]) / 4.0
            area_m2 = polygon_area_m2(polygon[:-1])
            zone = {
                "type": zone_type,
                "severity": severity,
                "confidence": confidence,
                "area_m2": area_m2,
                "centroid_lat": centroid_lat,
                "centroid_lon": centroid_lon,
                "polygon_geojson": {
                    "type": "Polygon",
                    "coordinates": [[[lon, lat] for lat, lon in polygon]],
                },
                "evidence_image_ids": capture_ids[: min(4, len(capture_ids))],
                "meta_data": {
                    "cluster_size": len(cluster),
                    "grid_bbox": {
                        "row0": patch_index.row0,
                        "col0": patch_index.col0,
                        "row1": patch_index.row1,
                        "col1": patch_index.col1,
                    },
                },
            }
            zones.append(zone)
            inspection_points.append(
                {
                    "zone_type": zone_type,
                    "lat": centroid_lat,
                    "lon": centroid_lon,
                    "label": f"Inspect {zone_type.replace('_', ' ')}",
                    "priority": clamp01((severity * 0.65) + (confidence * 0.35)),
                    "meta_data": {
                        "evidence_image_ids": zone["evidence_image_ids"],
                    },
                }
            )

    average_confidence = float(np.mean([zone["confidence"] for zone in zones])) if zones else 0.0
    summary = {
        "status": "completed",
        "total_anomaly_count": len(zones),
        "counts_by_type": {
            "under_irrigated": sum(1 for zone in zones if zone["type"] == "under_irrigated"),
            "overwatered": sum(1 for zone in zones if zone["type"] == "overwatered"),
            "uneven_distribution": sum(
                1 for zone in zones if zone["type"] == "uneven_distribution"
            ),
        },
        "average_confidence": average_confidence,
    }
    inspection_points.sort(key=lambda item: item["priority"], reverse=True)
    return {"zones": zones, "inspection_points": inspection_points, "summary": summary}
