from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from backend.services.irrigation.analytics import analyze_irrigation
from backend.services.irrigation.compositor import build_field_composite


@dataclass(frozen=True)
class FakeCapture:
    id: int
    lat: float
    lon: float
    alt_m: float
    image_uri: str


def _write_image(path: Path, color_bgr: tuple[int, int, int], *, width: int = 180, height: int = 120) -> None:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :] = color_bgr
    cv2.imwrite(str(path), image)


def test_build_field_composite_creates_preview_and_footprints(tmp_path: Path) -> None:
    capture_dir = tmp_path / "captures"
    output_dir = tmp_path / "outputs"
    capture_dir.mkdir()
    output_dir.mkdir()

    capture_a = capture_dir / "a.jpg"
    capture_b = capture_dir / "b.jpg"
    _write_image(capture_a, (20, 150, 30))
    _write_image(capture_b, (25, 180, 25))

    composite = build_field_composite(
        captures=[
            FakeCapture(id=1, lat=50.0, lon=4.0, alt_m=24.0, image_uri=str(capture_a)),
            FakeCapture(id=2, lat=50.00015, lon=4.00018, alt_m=24.0, image_uri=str(capture_b)),
        ],
        output_dir=output_dir,
    )

    assert composite.preview_path.exists()
    assert composite.preview_width > 0
    assert composite.preview_height > 0
    assert composite.resolution_m_per_px > 0
    assert len(composite.footprints) == 2


def test_analyze_irrigation_detects_under_over_and_uneven_regions(tmp_path: Path) -> None:
    preview = np.zeros((256, 256, 3), dtype=np.uint8)
    preview[:, :] = (30, 150, 35)  # healthy baseline
    preview[20:120, 15:110] = (70, 170, 180)  # bright dry/yellow patch
    preview[140:235, 20:120] = (120, 40, 20)  # dark wet patch
    preview[:, 170:210] = (55, 60, 150)  # elongated inconsistent band

    preview_path = tmp_path / "preview.png"
    cv2.imwrite(str(preview_path), preview)

    analysis = analyze_irrigation(
        preview_path=preview_path,
        resolution_m_per_px=0.2,
        bounds={
            "origin_lat": 50.0,
            "origin_lon": 4.0,
            "min_x_m": 0.0,
            "max_y_m": 51.2,
        },
        capture_ids=[1, 2, 3],
        patch_size_px=32,
    )

    zone_types = {zone["type"] for zone in analysis["zones"]}
    assert "under_irrigated" in zone_types
    assert "overwatered" in zone_types
    assert "uneven_distribution" in zone_types
    assert analysis["summary"]["total_anomaly_count"] >= 3
    assert analysis["summary"]["average_confidence"] > 0
    assert len(analysis["inspection_points"]) >= 3
