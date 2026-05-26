"""Download/cache built-in YOLO models used by offline video analysis.

Run from the repository root:
    python backend/scripts/download_video_analysis_models.py

Ultralytics downloads weights automatically on first use, but this script
prewarms backend-managed storage so the first analysis job is not delayed.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.modules.video_analysis.model_storage import ensure_model_file  # noqa: E402

MODELS = (
    "yolo26n.pt",  # fastest general object detector
    "yolo26s.pt",  # better/default general object detector
    "yolo26n-seg.pt",  # fast segmentation variant
    "yolo26s-seg.pt",  # better segmentation variant
)


def main() -> None:
    for model_name in MODELS:
        storage_path = ensure_model_file(model_name)
        print(f"Ready: {storage_path}")
    print("Done. Models are stored under backend/storage/ml_models/ultralytics/.")


if __name__ == "__main__":
    main()
