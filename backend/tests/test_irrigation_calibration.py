from pathlib import Path

import cv2
import numpy as np

from backend.modules.irrigation.domain.analytics import (
    IRRIGATION_ANALYTICS_CALIBRATION_VERSION,
    analyze_irrigation,
)


def test_irrigation_calibration_fixture_is_reproducible(tmp_path: Path) -> None:
    image = np.full((64, 64, 3), (40, 150, 40), dtype=np.uint8)
    image[16:48, 16:48] = (20, 80, 20)
    preview = tmp_path / "calibration.jpg"
    assert cv2.imwrite(str(preview), image)

    result = analyze_irrigation(
        preview_path=preview,
        resolution_m_per_px=0.1,
        bounds={"origin_lat": 50.0, "origin_lon": 4.0, "min_x_m": 0.0, "max_y_m": 6.4},
        capture_ids=[1],
    )

    assert result["summary"]["status"] == "completed"
    assert result["summary"]["calibration_version"] == IRRIGATION_ANALYTICS_CALIBRATION_VERSION
