from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import Any

from backend.modules.video_analysis.model_storage import ensure_model_file
from backend.modules.vision_models.service.trainers.base import (
    ProgressCallback,
    TrainerRequest,
    TrainerResult,
)
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record

logger = logging.getLogger(__name__)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _per_image_metrics(box: Any) -> list[dict[str, object]]:
    raw_metrics = getattr(box, "image_metrics", None)
    if not isinstance(raw_metrics, dict):
        return []
    output: list[dict[str, object]] = []
    for image_name, raw_values in sorted(raw_metrics.items()):
        if not isinstance(raw_values, dict):
            continue
        values: dict[str, object] = {"image_name": str(image_name)}
        for key in ("precision", "recall", "f1"):
            values[key] = _number(raw_values.get(key))
        for key in ("tp", "fp", "fn"):
            try:
                values[key] = int(raw_values.get(key, 0))
            except (TypeError, ValueError):
                values[key] = 0
        output.append(values)
    return output


def _result_metrics(result: Any, class_names: list[str]) -> dict[str, object]:
    results_dict = getattr(result, "results_dict", {}) or {}
    precision = _number(results_dict.get("metrics/precision(B)"))
    recall = _number(results_dict.get("metrics/recall(B)"))
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall > 0
        else None
    )
    box = getattr(result, "box", None)
    summary: dict[str, object] = {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "map50": _number(results_dict.get("metrics/mAP50(B)")),
        "map75": _number(getattr(box, "map75", None)),
        "map50_95": _number(results_dict.get("metrics/mAP50-95(B)")),
    }
    per_class: list[dict[str, object]] = []
    if box is not None and hasattr(box, "class_result"):
        class_indices = list(getattr(box, "ap_class_index", range(len(class_names))))
        for result_index, class_index in enumerate(class_indices):
            try:
                precision, recall, map50, map50_95 = box.class_result(result_index)
            except (IndexError, TypeError, ValueError):
                continue
            numeric_index = int(class_index)
            class_precision = _number(precision)
            class_recall = _number(recall)
            class_f1 = (
                2 * class_precision * class_recall / (class_precision + class_recall)
                if class_precision is not None
                and class_recall is not None
                and class_precision + class_recall > 0
                else None
            )
            all_ap = getattr(box, "all_ap", None)
            map75 = None
            if all_ap is not None:
                try:
                    map75 = _number(all_ap[result_index][5])
                except (IndexError, TypeError):
                    map75 = None
            per_class.append(
                {
                    "class_index": numeric_index,
                    "class_name": (
                        class_names[numeric_index]
                        if 0 <= numeric_index < len(class_names)
                        else str(numeric_index)
                    ),
                    "precision": class_precision,
                    "recall": class_recall,
                    "f1": class_f1,
                    "map50": _number(map50),
                    "map75": map75,
                    "map50_95": _number(map50_95),
                }
            )
    confusion_matrix = getattr(getattr(result, "confusion_matrix", None), "matrix", None)
    matrix = confusion_matrix.tolist() if hasattr(confusion_matrix, "tolist") else None
    raw_per_image = getattr(result, "per_image_stats", None)
    per_image = (
        raw_per_image
        if isinstance(raw_per_image, list)
        else _per_image_metrics(box)
    )
    return {
        "summary": summary,
        "per_class": per_class,
        "confusion_matrix": matrix,
        "confusion_matrix_labels": [*class_names, "background"] if matrix else [],
        "per_image": per_image,
    }


class UltralyticsTrainer:
    def train(
        self,
        request: TrainerRequest,
        progress_callback: ProgressCallback,
    ) -> TrainerResult:
        try:
            import torch
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("Ultralytics training dependencies are unavailable") from exc

        if request.requested_device == "auto":
            device: str | int = 0 if torch.cuda.is_available() else "cpu"
        else:
            device = request.requested_device
        device_label = f"cuda:{device}" if isinstance(device, int) else str(device)
        base_weights = ensure_model_file(request.base_model)
        model = YOLO(str(base_weights))

        def on_train_epoch_end(trainer: Any) -> None:
            epoch = int(getattr(trainer, "epoch", 0)) + 1
            raw_metrics = getattr(trainer, "metrics", {}) or {}
            progress_metrics = {
                str(key): value
                for key, raw_value in raw_metrics.items()
                if (value := _number(raw_value)) is not None
            }
            progress_callback(epoch, request.epochs, progress_metrics)

        model.add_callback("on_train_epoch_end", on_train_epoch_end)
        train_dir = request.output_dir / "training"
        model.train(
            data=str(request.data_config),
            epochs=request.epochs,
            imgsz=request.image_size,
            batch=request.batch_size,
            device=device,
            project=str(train_dir.parent),
            name=train_dir.name,
            exist_ok=True,
            pretrained=True,
            seed=0,
            deterministic=True,
            workers=request.dataloader_workers,
            plots=True,
            verbose=False,
            hsv_h=0.0,
            hsv_s=0.1,
            hsv_v=0.2,
            fliplr=0.5,
            flipud=0.1,
        )
        best = train_dir / "weights" / "best.pt"
        if not best.is_file():
            raise RuntimeError("Ultralytics training did not produce best.pt")

        evaluation_dir = request.output_dir / "evaluation"
        evaluator = YOLO(str(best))
        evaluation_started = time.monotonic()
        logger.info("evaluation_started split=test image_size=%d", request.image_size)
        try:
            evaluation = evaluator.val(
                data=str(request.data_config),
                split="test",
                imgsz=request.image_size,
                batch=request.batch_size,
                device=device,
                project=str(evaluation_dir.parent),
                name=evaluation_dir.name,
                exist_ok=True,
                plots=True,
                verbose=False,
            )
        except Exception:
            metric_add("model_evaluation_status", attrs={"status": "failed"})
            logger.exception("evaluation_failed split=test")
            raise
        duration_ms = (time.monotonic() - evaluation_started) * 1000.0
        metric_record("model_evaluation_duration", duration_ms, {"split": "test"})
        metric_add("model_evaluation_status", attrs={"status": "completed"})
        logger.info("evaluation_completed split=test duration_ms=%.1f", duration_ms)
        artifacts: dict[str, Path] = {}
        for name in (
            "confusion_matrix.png",
            "confusion_matrix_normalized.png",
            "PR_curve.png",
            "F1_curve.png",
            "P_curve.png",
            "R_curve.png",
        ):
            path = evaluation_dir / name
            if path.is_file():
                artifacts[name.removesuffix(".png")] = path
        for path in sorted(evaluation_dir.glob("val_batch*_pred.jpg"))[:3]:
            artifacts[path.stem] = path
        return TrainerResult(
            best_weights=best,
            device=device_label,
            metrics=_result_metrics(evaluation, request.class_names),
            evaluation_artifacts=artifacts,
        )
