from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from pydantic import ValidationError

from backend.modules.vision_models import annotation_operations, dataset_ingestion_operations
from backend.modules.vision_models.application import VisionApplication, VisionNotFound
from backend.modules.vision_models.models import (
    DatasetImage,
    DatasetVersion,
    VisionClass,
    VisionProject,
)
from backend.modules.vision_models.schemas import AnnotationReplace
from backend.modules.vision_models.service.dataset_service import assign_deterministic_splits
from backend.modules.vision_models.service.storage import VisionStorage
from backend.modules.vision_models.service.trainers.ultralytics import _result_metrics


@pytest.fixture
def vision_context(tmp_path, monkeypatch):
    project = VisionProject(
        id="project-1",
        org_id=7,
        name="Tomato detector",
        crop="tomato",
        created_by_user_id=1,
    )
    project.classes = [
        VisionClass(id="class-ripe", name="ripe", class_index=0),
        VisionClass(id="class-damaged", name="damaged", class_index=1),
    ]
    dataset = DatasetVersion(id="dataset-1", project=project, version=1)
    dataset.project_id = project.id
    image = DatasetImage(
        id="image-1",
        dataset=dataset,
        storage_uri="vision://projects/project-1/image.jpg",
        thumbnail_uri="vision://projects/project-1/thumb.jpg",
        source_type="upload",
        source_group="upload-1",
        width=3840,
        height=2160,
        sha256="a" * 64,
        selected=True,
        metadata_json={},
        annotation_status="unlabeled",
        created_at=datetime.now(UTC),
    )
    image.annotations = []
    image.dataset_id = dataset.id
    dataset.images = [image]

    class FakeRepository:
        def __init__(self, _db):
            pass

        async def get_image(self, image_id, user):
            return image if image_id == image.id and user.org_id == project.org_id else None

        async def all_dataset_images(self, dataset_id):
            return [image] if dataset_id == dataset.id else []

    class FakeDatabase:
        async def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [item.id for item in project.classes])

        async def execute(self, _statement):
            return None

        async def flush(self):
            now = datetime.now(UTC)
            for annotation in image.annotations:
                annotation.id = annotation.id or str(uuid4())
                annotation.annotation_type = annotation.annotation_type or "bbox"
                annotation.created_at = annotation.created_at or now
                annotation.updated_at = annotation.updated_at or now

        async def commit(self):
            await self.flush()

    async def run_inline(function, *args, **kwargs):
        runtime_keys = {"boundary", "operation", "timeout_s"}
        filtered = {
            key: value for key, value in kwargs.items() if key not in runtime_keys
        }
        return function(*args, **filtered)

    monkeypatch.setattr(annotation_operations, "VisionRepository", FakeRepository)
    monkeypatch.setattr(dataset_ingestion_operations, "VisionRepository", FakeRepository)
    monkeypatch.setattr(dataset_ingestion_operations, "run_blocking", run_inline)
    return (
        FakeDatabase(),
        VisionApplication(storage=VisionStorage(tmp_path)),
        SimpleNamespace(id=1, org_id=7),
    )


@pytest.mark.asyncio
async def test_annotation_create_update_class_change_delete_and_review_empty(vision_context):
    db, application, user = vision_context
    created = await application.replace_annotations(
        db,
        "image-1",
        AnnotationReplace(
            reviewed=False,
            annotations=[
                {
                    "class_id": "class-ripe",
                    "x1": 384,
                    "y1": 432,
                    "x2": 1152,
                    "y2": 1080,
                }
            ],
        ),
        user,
    )
    assert created.annotation_status == "labeled"
    assert created.annotations[0].class_id == "class-ripe"

    updated = await application.replace_annotations(
        db,
        "image-1",
        AnnotationReplace(
            reviewed=True,
            annotations=[
                {
                    "class_id": "class-damaged",
                    "x1": 576,
                    "y1": 540,
                    "x2": 1344,
                    "y2": 1188,
                }
            ],
        ),
        user,
    )
    assert updated.annotation_status == "reviewed"
    assert updated.annotations[0].class_id == "class-damaged"
    assert updated.annotations[0].x1 == pytest.approx(576)

    empty = await application.replace_annotations(
        db,
        "image-1",
        AnnotationReplace(reviewed=True, annotations=[]),
        user,
    )
    assert empty.annotations == []
    assert empty.annotation_status == "reviewed"


def test_annotation_contract_rejects_zero_size_and_out_of_bounds_coordinates():
    with pytest.raises(ValidationError):
        AnnotationReplace(
            annotations=[
                {"class_id": "class-ripe", "x1": 0.2, "y1": 0.2, "x2": 0.2, "y2": 0.5}
            ]
        )
    with pytest.raises(ValidationError):
        AnnotationReplace(
            annotations=[
                {
                    "class_id": "class-ripe",
                    "x1": 0,
                    "y1": 0,
                    "x2": float("inf"),
                    "y2": 10,
                }
            ]
        )
    with pytest.raises(ValidationError):
        AnnotationReplace(
            annotations=[
                {"class_id": "class-ripe", "x1": -0.1, "y1": 0.2, "x2": 0.3, "y2": 0.5}
            ]
        )


@pytest.mark.asyncio
async def test_annotation_access_is_tenant_scoped(vision_context):
    db, application, _user = vision_context
    with pytest.raises(VisionNotFound):
        await application.replace_annotations(
            db,
            "image-1",
            AnnotationReplace(reviewed=True, annotations=[]),
            SimpleNamespace(id=2, org_id=8),
        )


@pytest.mark.asyncio
async def test_annotation_rejects_original_image_out_of_bounds_coordinates(vision_context):
    db, application, user = vision_context
    with pytest.raises(VisionNotFound):
        await application.replace_annotations(
            db,
            "missing-image",
            AnnotationReplace(reviewed=False, annotations=[]),
            user,
        )
    with pytest.raises(ValueError, match="original image bounds"):
        await application.replace_annotations(
            db,
            "image-1",
            AnnotationReplace(
                annotations=[
                    {
                        "class_id": "class-ripe",
                        "x1": 3800,
                        "y1": 100,
                        "x2": 3900,
                        "y2": 200,
                    }
                ]
            ),
            user,
        )


def test_ultralytics_evaluation_metrics_are_normalized_without_stdout_parsing():
    class BoxMetrics:
        ap_class_index = np.asarray([0, 1])
        all_ap = np.asarray(
            [[0.92, 0.90, 0.88, 0.84, 0.80, 0.77, 0.74, 0.71, 0.68, 0.65], [0.8] * 10]
        )
        map75 = 0.735

        @staticmethod
        def class_result(index: int):
            return [(0.95, 0.9, 0.94, 0.72), (0.82, 0.71, 0.78, 0.51)][index]

    result = SimpleNamespace(
        results_dict={
            "metrics/precision(B)": 0.928,
            "metrics/recall(B)": 0.871,
            "metrics/mAP50(B)": 0.913,
            "metrics/mAP50-95(B)": 0.683,
        },
        box=BoxMetrics(),
        confusion_matrix=SimpleNamespace(matrix=np.asarray([[8, 1], [2, 7]])),
        per_image_stats=None,
    )
    result.box.image_metrics = {
        "image-1.jpg": {
            "precision": np.float64(0.8),
            "recall": np.float64(0.75),
            "f1": np.float64(0.774),
            "tp": np.int64(8),
            "fp": np.int64(1),
            "fn": np.int64(2),
        }
    }

    metrics = _result_metrics(result, ["ripe", "damaged"])

    assert metrics["summary"]["precision"] == pytest.approx(0.928)
    assert metrics["summary"]["map75"] == pytest.approx(0.735)
    assert metrics["summary"]["f1"] == pytest.approx(0.8986, rel=1e-3)
    assert metrics["per_class"][0]["class_name"] == "ripe"
    assert metrics["per_class"][0]["map75"] == pytest.approx(0.77)
    assert metrics["confusion_matrix"] == [[8, 1], [2, 7]]
    assert metrics["per_image"][0]["fn"] == 2
    assert metrics["per_image"][0]["image_name"] == "image-1.jpg"


def test_dataset_splits_keep_source_groups_together_and_are_deterministic():
    images = [
        SimpleNamespace(
            id=f"image-{index}",
            selected=True,
            source_group=f"source-{index // 2}",
            timestamp_seconds=float(index),
            frame_index=index,
            sha256=f"{index:064d}",
            split=None,
        )
        for index in range(8)
    ]

    assign_deterministic_splits(images)
    first_assignment = {image.id: image.split for image in images}
    assign_deterministic_splits(list(reversed(images)))

    assert {image.id: image.split for image in images} == first_assignment
    for source_group in {image.source_group for image in images}:
        assert len({image.split for image in images if image.source_group == source_group}) == 1
    assert {image.split for image in images} == {"train", "val", "test"}


def test_openapi_publishes_vision_and_video_tracking_contracts():
    from backend.entrypoints.api.app import app

    schema = app.openapi()
    paths = schema["paths"]
    assert {
        "/vision/projects",
        "/vision/images/{image_id}/annotations",
        "/vision/model-versions/{version_id}/evaluation",
        "/video-analysis/jobs/{job_id}/summary",
    } <= paths.keys()
    components = schema["components"]["schemas"]
    annotation = components[
        "backend__modules__vision_models__schemas__AnnotationOut"
    ]["properties"]
    assert {"class_id", "x1", "y1", "x2", "y2"} <= annotation.keys()
    evaluation = components["ModelEvaluationOut"]["properties"]
    assert {"summary", "per_class", "confusion_matrix", "artifacts"} <= evaluation.keys()
    analyze = components["AnalyzeVideoRequest"]["properties"]
    assert {
        "model_version_id",
        "small_object_mode",
        "tracking_enabled",
        "tracker_type",
    } <= analyze.keys()
    summary = components["VideoAnalysisSummaryOut"]["properties"]
    assert "unique_tracked_objects_by_class" in summary
