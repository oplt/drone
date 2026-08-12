from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np

from backend.modules.video_analysis.model_storage import ensure_model_file
from backend.modules.vision_models.config import vision_settings


@dataclass(frozen=True)
class FrameDetection:
    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float
    raw: dict[str, Any]
    track_id: int | None = None


class FrameDetector(Protocol):
    model_version: str

    def predict(self, image_bgr: np.ndarray) -> list[FrameDetection]: ...


def _resolved_model_path(model_name: str, model_path: str | Path | None) -> Path:
    resolved = Path(model_path) if model_path is not None else ensure_model_file(model_name)
    if not resolved.is_file():
        raise FileNotFoundError("Model weights are unavailable")
    return resolved.resolve()


def _artifact_version(model_name: str, model_path: Path) -> str:
    stat = model_path.stat()
    return f"{model_name}:{stat.st_size}:{stat.st_mtime_ns}"


@lru_cache(maxsize=8)
def load_yolo_model(model_path: str) -> Any:
    try:
        from ultralytics import YOLO

        return YOLO(model_path)
    except ImportError as exc:
        raise RuntimeError(
            "YOLO runtime dependencies are unavailable in the analysis worker. "
            "Install requirements.txt in the Python environment running Celery."
        ) from exc


class YoloFrameDetector:
    """Standard full-frame Ultralytics detector."""

    def __init__(
        self,
        model_name: str,
        confidence_threshold: float = 0.35,
        *,
        model_path: str | Path | None = None,
    ) -> None:
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.model_path = _resolved_model_path(model_name, model_path)
        self.model_version = _artifact_version(model_name, self.model_path)
        self.model = load_yolo_model(str(self.model_path))

    def predict(self, image_bgr: np.ndarray) -> list[FrameDetection]:
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
            coordinates = box.xyxy[0].detach().cpu().numpy().astype(float).tolist()
            confidence = float(box.conf[0].detach().cpu().item())
            class_id = int(box.cls[0].detach().cpu().item())
            detections.append(
                FrameDetection(
                    label=str(names.get(class_id, class_id)),
                    confidence=confidence,
                    x1=coordinates[0],
                    y1=coordinates[1],
                    x2=coordinates[2],
                    y2=coordinates[3],
                    raw={
                        "inference_mode": "standard",
                        "model": self.model_name,
                        "model_version": self.model_version,
                        "class_id": class_id,
                        "xyxy": coordinates,
                    },
                )
            )
        return detections


class SahiYoloFrameDetector:
    """SAHI sliced detector returning boxes in original full-frame coordinates."""

    def __init__(
        self,
        model_name: str,
        confidence_threshold: float = 0.35,
        *,
        model_path: str | Path | None = None,
        slice_height: int | None = None,
        slice_width: int | None = None,
        overlap_height_ratio: float | None = None,
        overlap_width_ratio: float | None = None,
        postprocess_match_threshold: float | None = None,
    ) -> None:
        try:
            import torch
            from sahi import AutoDetectionModel
        except ImportError as exc:
            raise RuntimeError(
                "Small-object analysis requires the SAHI runtime. "
                "Install backend requirements in the video worker."
            ) from exc

        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.model_path = _resolved_model_path(model_name, model_path)
        self.model_version = _artifact_version(model_name, self.model_path)
        self.slice_height = slice_height or vision_settings.video_sahi_slice_height
        self.slice_width = slice_width or vision_settings.video_sahi_slice_width
        self.overlap_height_ratio = (
            overlap_height_ratio
            if overlap_height_ratio is not None
            else vision_settings.video_sahi_overlap_height_ratio
        )
        self.overlap_width_ratio = (
            overlap_width_ratio
            if overlap_width_ratio is not None
            else vision_settings.video_sahi_overlap_width_ratio
        )
        self.postprocess_match_threshold = (
            postprocess_match_threshold
            if postprocess_match_threshold is not None
            else vision_settings.video_sahi_postprocess_match_threshold
        )
        self.model = AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model_path=str(self.model_path),
            confidence_threshold=confidence_threshold,
            device="cuda:0" if torch.cuda.is_available() else "cpu",
        )

    def predict(self, image_bgr: np.ndarray) -> list[FrameDetection]:
        try:
            from sahi.predict import get_sliced_prediction
        except ImportError as exc:
            raise RuntimeError("Small-object analysis requires the SAHI runtime.") from exc

        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        result = get_sliced_prediction(
            image_rgb,
            self.model,
            slice_height=self.slice_height,
            slice_width=self.slice_width,
            overlap_height_ratio=self.overlap_height_ratio,
            overlap_width_ratio=self.overlap_width_ratio,
            postprocess_type="NMS",
            postprocess_match_metric="IOU",
            postprocess_match_threshold=self.postprocess_match_threshold,
            postprocess_class_agnostic=False,
            perform_standard_pred=True,
            verbose=0,
        )
        detections: list[FrameDetection] = []
        for prediction in result.object_prediction_list:
            coordinates = [float(value) for value in prediction.bbox.to_xyxy()]
            category_id = int(prediction.category.id)
            detections.append(
                FrameDetection(
                    label=str(prediction.category.name),
                    confidence=float(prediction.score.value),
                    x1=coordinates[0],
                    y1=coordinates[1],
                    x2=coordinates[2],
                    y2=coordinates[3],
                    raw={
                        "inference_mode": "sahi",
                        "model": self.model_name,
                        "model_version": self.model_version,
                        "class_id": category_id,
                        "xyxy": coordinates,
                        "sahi": {
                            "slice_height": self.slice_height,
                            "slice_width": self.slice_width,
                            "overlap_height_ratio": self.overlap_height_ratio,
                            "overlap_width_ratio": self.overlap_width_ratio,
                            "postprocess_match_threshold": self.postprocess_match_threshold,
                        },
                    },
                )
            )
        return detections


def create_frame_detector(
    model_name: str,
    confidence_threshold: float = 0.35,
    *,
    model_path: str | Path | None = None,
    small_object_mode: bool = False,
) -> FrameDetector:
    detector_type = SahiYoloFrameDetector if small_object_mode else YoloFrameDetector
    return detector_type(
        model_name=model_name,
        confidence_threshold=confidence_threshold,
        model_path=model_path,
    )
