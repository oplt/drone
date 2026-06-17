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
    # 4-connected connected components. cv2 runs the labelling in native code,
    # replacing the O(rows*cols) pure-Python BFS. Results are equivalent for
    # downstream consumers, which only use per-cluster bbox/score aggregates
    # (order-independent).
    binary = np.ascontiguousarray(mask, dtype=np.uint8)
    if not binary.any():
        return []
    count, labels = cv2.connectedComponents(binary, connectivity=4)
    if count <= 1:
        return []
    order = np.argsort(labels.ravel(), kind="stable")
    sorted_labels = labels.ravel()[order]
    # Boundaries between label groups in the flattened, label-sorted index array.
    boundaries = np.flatnonzero(np.diff(sorted_labels)) + 1
    groups = np.split(order, boundaries)
    clusters: list[list[tuple[int, int]]] = []
    for group in groups:
        if labels.ravel()[group[0]] == 0:
            continue  # background
        rows_idx, cols_idx = np.unravel_index(group, mask.shape)
        clusters.append(list(zip(rows_idx.tolist(), cols_idx.tolist(), strict=True)))
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

    # Vectorized patch aggregation: pad the image up to a whole number of
    # patches (padding stays invalid because brightness 0.0 <= 0.02), reshape
    # into (rows, patch, cols, patch) blocks, and reduce per patch. Replaces the
    # rows*cols Python loop with a handful of NumPy reductions.
    padded_h = rows * patch_size_px
    padded_w = cols * patch_size_px

    def _pad(channel: np.ndarray) -> np.ndarray:
        out = np.zeros((padded_h, padded_w), dtype=np.float32)
        out[:canvas_height, :canvas_width] = channel
        return out

    def _blocks(channel: np.ndarray) -> np.ndarray:
        return channel.reshape(rows, patch_size_px, cols, patch_size_px).swapaxes(1, 2)

    block_brightness = _blocks(_pad(brightness))
    block_exg = _blocks(_pad(green_excess))
    block_saturation = _blocks(_pad(saturation))

    valid_px = block_brightness > 0.02
    valid_px_f = valid_px.astype(np.float32)
    counts = valid_px.reshape(rows, cols, -1).sum(axis=2)
    valid_grid = counts >= 16

    safe_counts = np.where(counts > 0, counts, 1).astype(np.float32)
    exg_grid = (block_exg * valid_px_f).reshape(rows, cols, -1).sum(axis=2) / safe_counts
    brightness_grid = (block_brightness * valid_px_f).reshape(rows, cols, -1).sum(
        axis=2
    ) / safe_counts
    saturation_grid = (block_saturation * valid_px_f).reshape(rows, cols, -1).sum(
        axis=2
    ) / safe_counts

    # Match the original: cells below the validity threshold stay zeroed.
    exg_grid = np.where(valid_grid, exg_grid, 0.0).astype(np.float32)
    brightness_grid = np.where(valid_grid, brightness_grid, 0.0).astype(np.float32)
    saturation_grid = np.where(valid_grid, saturation_grid, 0.0).astype(np.float32)

    valid_values = valid_grid
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
    under_score[valid_values] = (
        np.maximum(-exg_z[valid_values], 0.0) + np.maximum(bright_z[valid_values], 0.0) * 0.35
    )
    over_score[valid_values] = (
        np.maximum(-bright_z[valid_values], 0.0) + np.maximum(-sat_z[valid_values], 0.0) * 0.25
    )
    uneven_full = (
        np.abs(row_z)[:, None] * 0.6
        + np.abs(col_z)[None, :] * 0.4
        + np.abs(exg_z) * 0.25
    )
    uneven_score = np.where(valid_grid, uneven_full, 0.0).astype(np.float32)

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
