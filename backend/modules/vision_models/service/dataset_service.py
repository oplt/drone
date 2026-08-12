from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import cv2
import numpy as np
import yaml

from backend.modules.vision_models.models import DatasetImage, DatasetVersion, VisionClass
from backend.modules.vision_models.service.frame_curation import assess_quality, average_hash
from backend.modules.vision_models.service.storage import VisionStorage


class DatasetServiceError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedImage:
    storage_uri: str
    thumbnail_uri: str
    width: int
    height: int
    sha256: str
    perceptual_hash: str
    quality_score: float
    metadata: dict[str, Any]


def _encode_jpeg(image_bgr: np.ndarray, quality: int) -> bytes:
    ok, encoded = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise DatasetServiceError("Image could not be encoded")
    return encoded.tobytes()


def prepare_uploaded_image(
    content: bytes,
    *,
    filename: str,
    content_type: str | None,
    project_id: str,
    dataset_version: int,
    storage: VisionStorage,
) -> PreparedImage:
    array = np.frombuffer(content, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise DatasetServiceError(f"{filename}: invalid or unsupported image")
    height, width = image.shape[:2]
    if width < 32 or height < 32:
        raise DatasetServiceError(f"{filename}: image dimensions are too small")

    image_bytes = _encode_jpeg(image, 95)
    digest = hashlib.sha256(image_bytes).hexdigest()
    image_id = str(uuid4())
    image_path = storage.project_path(
        project_id, "datasets", f"v{dataset_version}", "images", f"{image_id}.jpg"
    )
    thumbnail_path = storage.project_path(
        project_id,
        "datasets",
        f"v{dataset_version}",
        "thumbnails",
        f"{image_id}.jpg",
    )
    image_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(image_bytes)
    thumb_width = min(360, width)
    thumb_height = max(1, round(height * thumb_width / width))
    thumbnail = cv2.resize(image, (thumb_width, thumb_height), interpolation=cv2.INTER_AREA)
    thumbnail_path.write_bytes(_encode_jpeg(thumbnail, 82))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    quality = assess_quality(image)
    return PreparedImage(
        storage_uri=storage.to_uri(image_path),
        thumbnail_uri=storage.to_uri(thumbnail_path),
        width=width,
        height=height,
        sha256=digest,
        perceptual_hash=average_hash(gray),
        quality_score=quality.score,
        metadata={
            "original_filename": Path(filename).name,
            "content_type": content_type,
            "quality": {
                "blur_variance": quality.blur_variance,
                "mean_exposure": quality.mean_exposure,
                "rejection_reasons": quality.rejection_reasons,
            },
        },
    )


def _split_counts(total: int) -> tuple[int, int, int]:
    if total <= 0:
        return 0, 0, 0
    if total == 1:
        return 1, 0, 0
    if total == 2:
        return 1, 1, 0
    train = max(1, int(total * 0.7))
    val = max(1, int(total * 0.2))
    test = total - train - val
    if test < 1:
        train = max(1, train - (1 - test))
        test = 1
    return train, val, test


def assign_deterministic_splits(images: list[DatasetImage]) -> None:
    """Assign source-safe splits; a single source uses contiguous capture blocks."""
    for image in images:
        if not image.selected:
            image.split = None
    selected = [image for image in images if image.selected]
    if not selected:
        return
    groups: dict[str, list[DatasetImage]] = defaultdict(list)
    for image in selected:
        groups[image.source_group].append(image)

    if len(groups) == 1:
        ordered = sorted(
            selected,
            key=lambda item: (
                item.timestamp_seconds if item.timestamp_seconds is not None else float("inf"),
                item.frame_index if item.frame_index is not None else 2**31,
                item.sha256,
            ),
        )
        train_count, val_count, _ = _split_counts(len(ordered))
        for index, image in enumerate(ordered):
            image.split = (
                "train"
                if index < train_count
                else "val"
                if index < train_count + val_count
                else "test"
            )
        return

    ordered_groups = sorted(
        groups.items(), key=lambda item: hashlib.sha256(item[0].encode()).hexdigest()
    )
    train_groups, val_groups, _ = _split_counts(len(ordered_groups))
    for index, (_, group_images) in enumerate(ordered_groups):
        split = (
            "train"
            if index < train_groups
            else "val"
            if index < train_groups + val_groups
            else "test"
        )
        for image in group_images:
            image.split = split


def dataset_manifest(dataset: DatasetVersion, images: list[DatasetImage]) -> dict[str, Any]:
    rows = []
    for image in sorted(images, key=lambda item: item.id):
        rows.append(
            {
                "id": image.id,
                "sha256": image.sha256,
                "source_type": image.source_type,
                "source_group": image.source_group,
                "source_video_id": image.source_video_id,
                "frame_index": image.frame_index,
                "timestamp_seconds": image.timestamp_seconds,
                "selected": image.selected,
                "split": image.split,
                "annotation_status": image.annotation_status,
                "annotations": sorted(
                    [
                        {
                            "class_id": annotation.class_id,
                            "x1": annotation.x1,
                            "y1": annotation.y1,
                            "x2": annotation.x2,
                            "y2": annotation.y2,
                            "source": annotation.source,
                        }
                        for annotation in image.annotations
                    ],
                    key=lambda item: (
                        item["class_id"],
                        item["x1"],
                        item["y1"],
                    ),
                ),
            }
        )
    return {"dataset_id": dataset.id, "version": dataset.version, "images": rows}


def manifest_checksum(manifest: dict[str, Any]) -> str:
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def write_manifest(
    dataset: DatasetVersion,
    project_id: str,
    images: list[DatasetImage],
    storage: VisionStorage,
) -> str:
    manifest = dataset_manifest(dataset, images)
    checksum = manifest_checksum(manifest)
    manifest["checksum"] = checksum
    path = storage.project_path(project_id, "datasets", f"v{dataset.version}", "manifest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return checksum


def build_yolo_dataset(
    *,
    project_id: str,
    dataset: DatasetVersion,
    images: list[DatasetImage],
    classes: list[VisionClass],
    output_dir: Path,
    storage: VisionStorage,
) -> Path:
    if not images:
        raise DatasetServiceError("Dataset contains no selected images")
    class_index = {item.id: item.class_index for item in classes}
    output_dir.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val", "test"):
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    for image in images:
        if not image.selected or image.split not in {"train", "val", "test"}:
            continue
        source = storage.resolve_uri(image.storage_uri)
        target_image = output_dir / "images" / image.split / f"{image.id}.jpg"
        shutil.copy2(source, target_image)
        label_rows: list[str] = []
        for annotation in image.annotations:
            index = class_index.get(annotation.class_id)
            if index is None:
                raise DatasetServiceError("Annotation references an unknown class")
            center_x = (annotation.x1 + annotation.x2) / (2 * image.width)
            center_y = (annotation.y1 + annotation.y2) / (2 * image.height)
            width = (annotation.x2 - annotation.x1) / image.width
            height = (annotation.y2 - annotation.y1) / image.height
            label_rows.append(f"{index} {center_x:.8f} {center_y:.8f} {width:.8f} {height:.8f}")
        (output_dir / "labels" / image.split / f"{image.id}.txt").write_text(
            "\n".join(label_rows), encoding="utf-8"
        )

    data = {
        "path": str(output_dir.resolve()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": [item.name for item in sorted(classes, key=lambda item: item.class_index)],
    }
    config_path = output_dir / "data.yaml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return config_path


def build_yolo_export(
    *,
    project_id: str,
    dataset: DatasetVersion,
    images: list[DatasetImage],
    classes: list[VisionClass],
    storage: VisionStorage,
) -> Path:
    export_root = storage.project_path(
        project_id, "datasets", f"v{dataset.version}", "exports", str(uuid4())
    )
    build_yolo_dataset(
        project_id=project_id,
        dataset=dataset,
        images=images,
        classes=classes,
        output_dir=export_root,
        storage=storage,
    )
    archive_path = export_root.with_suffix(".zip")
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in export_root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(export_root))
    return archive_path


def parse_yolo_annotation_zip(
    content: bytes,
    *,
    image_ids: set[str],
    class_ids: list[str],
) -> dict[str, list[tuple[str, float, float, float, float]]]:
    from io import BytesIO

    parsed: dict[str, list[tuple[str, float, float, float, float]]] = {}
    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise DatasetServiceError("Annotation import must be a ZIP archive") from exc
    with archive:
        if len(archive.infolist()) > 20_000:
            raise DatasetServiceError("Annotation archive contains too many files")
        for info in archive.infolist():
            path = Path(info.filename)
            if path.is_absolute() or ".." in path.parts or path.suffix.lower() != ".txt":
                continue
            image_id = path.stem
            if image_id not in image_ids:
                continue
            rows: list[tuple[str, float, float, float, float]] = []
            text_content = archive.read(info).decode("utf-8")
            for line_number, line in enumerate(text_content.splitlines(), start=1):
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) != 5:
                    raise DatasetServiceError(
                        f"{info.filename}:{line_number}: expected five YOLO values"
                    )
                class_index_value = int(parts[0])
                if class_index_value < 0 or class_index_value >= len(class_ids):
                    raise DatasetServiceError(
                        f"{info.filename}:{line_number}: class index is out of range"
                    )
                center_x, center_y, width, height = map(float, parts[1:])
                x1, y1 = center_x - width / 2, center_y - height / 2
                x2, y2 = center_x + width / 2, center_y + height / 2
                if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
                    raise DatasetServiceError(
                        f"{info.filename}:{line_number}: box is outside normalized bounds"
                    )
                rows.append((class_ids[class_index_value], x1, y1, x2, y2))
            parsed[image_id] = rows
    return parsed
