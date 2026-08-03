"""Typed model boundaries; domain code never imports Ultralytics directly."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelPrediction:
    label: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float] | None = None
    mask_geojson: dict[str, Any] | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


class DetectionModelAdapter(Protocol):
    model_version: str
    def predict(self, image_bgr: Any) -> list[ModelPrediction]: ...


class SegmentationModelAdapter(Protocol):
    model_version: str
    def segment(self, image_bgr: Any) -> list[ModelPrediction]: ...


class TrackingAdapter(Protocol):
    def update(self, predictions: list[ModelPrediction], timestamp_seconds: float) -> list[ModelPrediction]: ...


class UltralyticsDetectionAdapter:
    """Optional adapter around the existing detector implementation."""

    def __init__(self, detector: Any):
        self.detector = detector
        self.model_version = str(getattr(detector, "model_version", "unknown"))

    def predict(self, image_bgr: Any) -> list[ModelPrediction]:
        return [ModelPrediction(label=item.label, confidence=float(item.confidence), bbox_xyxy=(float(item.x1), float(item.y1), float(item.x2), float(item.y2)), attributes=dict(getattr(item, "raw", {}) or {})) for item in self.detector.predict(image_bgr)]


class OptionalEdgeAdapter:
    """Use Jetson/edge callable when configured; otherwise use CPU adapter."""

    def __init__(self, *, edge_predict: Any | None = None, cpu_adapter: DetectionModelAdapter | None = None):
        self.edge_predict = edge_predict
        self.cpu_adapter = cpu_adapter
        self.model_version = "edge" if edge_predict is not None else str(getattr(cpu_adapter, "model_version", "cpu"))

    def predict(self, image_bgr: Any) -> list[ModelPrediction]:
        if self.edge_predict is not None:
            return list(self.edge_predict(image_bgr))
        if self.cpu_adapter is None:
            return []
        return self.cpu_adapter.predict(image_bgr)
