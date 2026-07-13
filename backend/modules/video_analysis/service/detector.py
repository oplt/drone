from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from backend.modules.video_analysis.model_storage import ensure_model_file


@dataclass(frozen=True)
class FrameDetection:
    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float
    raw: dict[str, Any]


@lru_cache(maxsize=4)
def load_yolo_model(model_name: str) -> Any:
    """Load and cache model weights.

    Examples:
    - yolo26n.pt       fastest general detector
    - yolo26s.pt       better/default detector
    - yolo26n-seg.pt   fast segmentation
    - yolo26s-seg.pt   better segmentation
    - storage/ml_models/agriculture/best.pt  local fine-tuned model, stored under backend/
    """
    try:
        from ultralytics import YOLO

        return YOLO(str(ensure_model_file(model_name)))
    except ImportError as exc:
        raise RuntimeError(
            "YOLO runtime dependencies are unavailable in the analysis worker. "
            "Install requirements.txt in the Python environment running Celery."
        ) from exc


class YoloFrameDetector:
    def __init__(self, model_name: str, confidence_threshold: float = 0.35):
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.model_path = ensure_model_file(model_name)
        stat = Path(self.model_path).stat()
        self.model_version = f"{model_name}:{stat.st_size}:{stat.st_mtime_ns}"
        self.model = load_yolo_model(model_name)

    def predict(self, image_bgr: np.ndarray) -> list[FrameDetection]:
        # Ultralytics accepts BGR numpy arrays. verbose=False keeps workers quiet.
        result = self.model.predict(
            source=image_bgr,
            conf=self.confidence_threshold,
            verbose=False,
        )[0]

        names = result.names or {}
        detections: list[FrameDetection] = []

        if result.boxes is None:
            return detections

        for box in result.boxes:
            xyxy = box.xyxy[0].detach().cpu().numpy().astype(float).tolist()
            conf = float(box.conf[0].detach().cpu().item())
            cls_id = int(box.cls[0].detach().cpu().item())
            label = str(names.get(cls_id, cls_id))

            detections.append(
                FrameDetection(
                    label=label,
                    confidence=conf,
                    x1=xyxy[0],
                    y1=xyxy[1],
                    x2=xyxy[2],
                    y2=xyxy[3],
                    raw={
                        "model": self.model_name,
                        "model_version": self.model_version,
                        "class_id": cls_id,
                        "xyxy": xyxy,
                    },
                )
            )

        return detections
