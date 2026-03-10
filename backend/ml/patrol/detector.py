from __future__ import annotations

import logging
from typing import List

from backend.ml.patrol.models import Detection, FramePacket

log = logging.getLogger(__name__)
DEFAULT_ALLOWED_LABELS = frozenset(
    {"person", "car", "truck", "bus", "motorcycle", "bicycle", "dog", "cat"}
)

try:
    import torch
    from ultralytics import YOLO
except Exception:  # pragma: no cover - optional dependency
    torch = None
    YOLO = None


class ObjectDetector:
    def __init__(
        self,
        model_path: str,
        conf: float = 0.35,
        iou: float = 0.45,
        allowed_labels: set[str] | frozenset[str] | None = None,
    ):
        self.model_path = model_path
        self.conf = float(conf)
        self.iou = float(iou)
        self.allowed = frozenset(allowed_labels or DEFAULT_ALLOWED_LABELS)
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        if YOLO is None:
            raise RuntimeError(
                "ultralytics is not installed. Install 'ultralytics' and a compatible torch build to enable ML detection."
            )
        self._model = YOLO(self.model_path)
        return self._model

    def detect(self, packet: FramePacket) -> List[Detection]:
        model = self._ensure_model()
        detections: list[Detection] = []

        if torch is None:
            raise RuntimeError("torch is not installed; detector cannot run")

        with torch.inference_mode():
            results = model.predict(
                source=packet.image,
                conf=self.conf,
                iou=self.iou,
                verbose=False,
            )

        for result in results:
            names = result.names
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                cls_id = int(box.cls[0].item())
                label = str(names[cls_id])
                if label not in self.allowed:
                    continue
                conf = float(box.conf[0].item())
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                detections.append(Detection(label=label, confidence=conf, bbox=(x1, y1, x2, y2)))

        return detections
