from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import numpy as np
import pytest
from pydantic import ValidationError

from backend.modules.vision_models import (
    annotation_operations,
    dataset_ingestion_operations,
    project_operations,
    training_operations,
)
from backend.modules.vision_models.application import (
    VisionAnnotationConflict,
    VisionApplication,
    VisionNotFound,
)
from backend.modules.vision_models.models import (
    Annotation,
    DatasetImage,
    DatasetVersion,
    VisionClass,
    VisionProject,
)
from backend.modules.vision_models.schemas import AnnotationReplace
from backend.modules.vision_models.service import frame_curation
from backend.modules.vision_models.service.dataset_service import assign_deterministic_splits
from backend.modules.vision_models.service.frame_curation import FrameQuality
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
        annotation_revision=0,
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

        async def claim_annotation_revision(self, image_id, *, expected_revision):
            if image_id != image.id or image.annotation_revision != expected_revision:
                return None
            image.annotation_revision += 1
            return image.annotation_revision

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

        async def rollback(self):
            return None

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
            expected_revision=0,
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
            expected_revision=1,
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
        AnnotationReplace(expected_revision=2, reviewed=True, annotations=[]),
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
            AnnotationReplace(expected_revision=0, reviewed=True, annotations=[]),
            SimpleNamespace(id=2, org_id=8),
        )


@pytest.mark.asyncio
async def test_annotation_rejects_original_image_out_of_bounds_coordinates(vision_context):
    db, application, user = vision_context
    with pytest.raises(VisionNotFound):
        await application.replace_annotations(
            db,
            "missing-image",
            AnnotationReplace(expected_revision=0, reviewed=False, annotations=[]),
            user,
        )
    with pytest.raises(ValueError, match="original image bounds"):
        await application.replace_annotations(
            db,
            "image-1",
            AnnotationReplace(
                expected_revision=0,
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


@pytest.mark.asyncio
async def test_stale_annotation_revision_never_overwrites_server_state(vision_context):
    db, application, user = vision_context
    saved = await application.replace_annotations(
        db,
        "image-1",
        AnnotationReplace(
            expected_revision=0,
            reviewed=True,
            annotations=[
                {
                    "class_id": "class-ripe",
                    "x1": 10,
                    "y1": 10,
                    "x2": 100,
                    "y2": 100,
                }
            ],
        ),
        user,
    )
    with pytest.raises(VisionAnnotationConflict) as conflict:
        await application.replace_annotations(
            db,
            "image-1",
            AnnotationReplace(expected_revision=0, reviewed=True, annotations=[]),
            user,
        )
    assert conflict.value.current_revision == 1
    assert saved.annotation_revision == 1
    assert len(saved.annotations) == 1


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


def test_single_video_split_holds_temporal_boundary_frames():
    images = [
        SimpleNamespace(
            id=f"image-{index}",
            selected=True,
            source_group="video:one",
            timestamp_seconds=float(index),
            frame_index=index,
            sha256=f"{index:064d}",
            perceptual_hash=f"{(index * 0x9E3779B97F4A7C15) & ((1 << 64) - 1):016x}",
            split=None,
        )
        for index in range(15)
    ]

    summary = assign_deterministic_splits(images, temporal_exclusion_buffer=1)

    assert summary["held_boundary_frames"] >= 2
    assert any(image.split is None for image in images)
    assert {image.split for image in images if image.split} == {"train", "val", "test"}
    assert "nearest_cross_split_similarity_count" in summary


def test_frame_curation_comparisons_are_window_bounded(tmp_path, monkeypatch):
    frame_count = 300
    hashes = iter(
        f"{(index * 0x9E3779B97F4A7C15) & ((1 << 64) - 1):016x}"
        for index in range(frame_count)
    )
    frames = [
        SimpleNamespace(
            frame_index=index,
            timestamp_seconds=float(index),
            image_bgr=np.full((240, 320, 3), index % 255, dtype=np.uint8),
        )
        for index in range(frame_count)
    ]
    monkeypatch.setattr(
        frame_curation,
        "read_video_metadata",
        lambda _path: SimpleNamespace(duration_seconds=float(frame_count)),
    )
    monkeypatch.setattr(
        frame_curation,
        "iter_frames",
        lambda _path, every_seconds: iter(frames),
    )
    monkeypatch.setattr(frame_curation, "average_hash", lambda _gray: next(hashes))
    monkeypatch.setattr(
        frame_curation,
        "assess_quality",
        lambda _image: FrameQuality(100.0, 127.0, 1.0, []),
    )

    result = frame_curation.curate_video_frames(
        "video.mp4", tmp_path, interval_seconds=1.0, max_frames=frame_count
    )

    assert result.comparison_count <= frame_count * (
        frame_curation.TEMPORAL_HASH_WINDOW + frame_curation.HASH_BUCKET_LIMIT
    )
    assert result.comparison_count < frame_count * frame_count // 2


@pytest.mark.asyncio
async def test_deploy_is_blocked_by_low_map50(monkeypatch):
    version = SimpleNamespace(
        id="version-1",
        model_id="model-1",
        status="candidate",
        training_run_id="run-1",
        dataset_id="dataset-1",
        metrics={"summary": {"map50": 0.1}},
        weights_uri="vision://weights.pt",
        checksum="a" * 64,
        classes=["weed"],
        model=SimpleNamespace(
            task_type="detection",
            project=SimpleNamespace(capability_id="object_detection"),
        ),
    )

    class FakeRepository:
        def __init__(self, _db):
            pass

        async def get_model_version(self, version_id, _user, **_kwargs):
            return version if version_id == version.id else None

    monkeypatch.setattr(training_operations, "VisionRepository", FakeRepository)
    app = VisionApplication()
    monkeypatch.setattr(app, "_verify_weights_checksum", AsyncMock(return_value=True))
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=None),
        get=AsyncMock(
            return_value=SimpleNamespace(
                version=1, test_count=3, manifest_checksum="c" * 64
            )
        ),
    )

    with pytest.raises(ValueError, match="map50"):
        await app.deploy_model(db, version.id, SimpleNamespace(id=1, org_id=7))


def test_upload_near_duplicate_clustering_deselects_secondary():
    from backend.modules.vision_models.service.dataset_service import (
        apply_dataset_near_duplicate_clustering,
    )

    shared_hash = "aaaaaaaaaaaaaaaa"
    images = [
        SimpleNamespace(
            id="img-1",
            selected=True,
            perceptual_hash=shared_hash,
            metadata_json={},
        ),
        SimpleNamespace(
            id="img-2",
            selected=True,
            perceptual_hash=shared_hash,
            metadata_json={},
        ),
        SimpleNamespace(
            id="img-3",
            selected=True,
            perceptual_hash="ffffffffffffffff",
            metadata_json={},
        ),
    ]
    summary = apply_dataset_near_duplicate_clustering(images)
    assert summary["duplicate_cluster_count"] == 1
    assert summary["near_duplicate_rejected"] == 1
    assert images[0].selected is True
    assert images[1].selected is False
    assert images[1].metadata_json["duplicate_cluster_id"].startswith("near-duplicate:")
    assert images[2].selected is True


def test_multi_source_split_reports_cross_split_near_duplicates():
    shared_hash = "bbbbbbbbbbbbbbbb"
    images = [
        SimpleNamespace(
            id="image-a",
            selected=True,
            source_group="video:a",
            timestamp_seconds=0.0,
            frame_index=0,
            sha256="1" * 64,
            perceptual_hash=shared_hash,
            split=None,
        ),
        SimpleNamespace(
            id="image-b",
            selected=True,
            source_group="video:b",
            timestamp_seconds=1.0,
            frame_index=1,
            sha256="2" * 64,
            perceptual_hash="1111111111111111",
            split=None,
        ),
        SimpleNamespace(
            id="image-c",
            selected=True,
            source_group="video:c",
            timestamp_seconds=2.0,
            frame_index=2,
            sha256="3" * 64,
            perceptual_hash=shared_hash,
            split=None,
        ),
    ]
    summary = assign_deterministic_splits(images)
    assert {image.split for image in images} == {"train", "val", "test"}
    assert summary["nearest_cross_split_similarity_count"] > 0


@pytest.mark.asyncio
async def test_create_training_run_blocks_when_split_leakage_policy_on(monkeypatch):
    from backend.modules.vision_models.schemas import TrainingRunCreate

    dataset = SimpleNamespace(
        id="dataset-1",
        project_id="project-1",
        status="locked",
        curation_summary={
            "split_leakage_risk": True,
            "quality_flags": {"split_leakage_risk": True},
        },
        manifest_checksum="checksum",
    )
    project = SimpleNamespace(id="project-1", classes=[SimpleNamespace(name="weed")])
    images = [
        SimpleNamespace(
            selected=True,
            annotation_status="reviewed",
            split=split,
        )
        for split in ("train", "val", "test")
    ]

    class FakeRepository:
        def __init__(self, _db):
            pass

        async def get_project(self, _project_id, _user):
            return project

        async def get_dataset(self, _dataset_id, _user):
            return dataset

        async def all_dataset_images(self, _dataset_id):
            return images

        @staticmethod
        def project_visible_to(_user):
            return True

    monkeypatch.setattr(training_operations, "VisionRepository", FakeRepository)
    monkeypatch.setattr(
        training_operations.vision_settings,
        "vision_require_curation_quality",
        True,
    )

    with pytest.raises(ValueError, match="curation quality"):
        await VisionApplication().create_training_run(
            SimpleNamespace(),
            "project-1",
            TrainingRunCreate(
                dataset_id="dataset-1", base_model="yolo26s.pt", preset="balanced"
            ),
            SimpleNamespace(id=1, org_id=7),
        )


@pytest.mark.asyncio
async def test_archive_blocks_the_sole_production_version(monkeypatch):
    version = SimpleNamespace(
        id="version-1",
        status="production",
        metrics={},
        checksum="a" * 64,
    )

    class FakeRepository:
        def __init__(self, _db):
            pass

        async def get_model_version(self, version_id, _user, **_kwargs):
            return version if version_id == version.id else None

    monkeypatch.setattr(training_operations, "VisionRepository", FakeRepository)

    with pytest.raises(RuntimeError, match="sole production"):
        await VisionApplication().archive_model(
            SimpleNamespace(), version.id, SimpleNamespace(id=1, org_id=7)
        )


def test_openapi_publishes_vision_and_video_tracking_contracts():
    from backend.entrypoints.api.app import app

    schema = app.openapi()
    paths = schema["paths"]
    assert {
        "/vision/projects",
        "/vision/images/{image_id}/annotations",
        "/vision/model-versions/{version_id}/evaluation",
        "/vision/model-versions/{version_id}/rollback",
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


@pytest.mark.asyncio
async def test_dataset_clone_reuses_immutable_media_and_copies_editable_metadata(
    monkeypatch,
):
    project = SimpleNamespace(id="project-1")
    source_dataset = SimpleNamespace(id="dataset-1", project_id=project.id)
    source_image = DatasetImage(
        id="image-1",
        dataset_id=source_dataset.id,
        storage_uri="vision://projects/project-1/images/content.jpg",
        thumbnail_uri="vision://projects/project-1/images/thumb.jpg",
        source_type="upload",
        source_group="batch-1",
        width=640,
        height=480,
        sha256="a" * 64,
        selected=True,
        split="train",
        annotation_status="reviewed",
        annotation_revision=4,
        metadata_json={"camera": "rgb"},
    )
    source_image.annotations = [
        Annotation(
            id="annotation-1",
            class_id="class-ripe",
            annotation_type="bbox",
            x1=10,
            y1=20,
            x2=100,
            y2=120,
            source="manual",
        )
    ]

    class FakeRepository:
        def __init__(self, _db):
            pass

        async def get_project(self, project_id, _user):
            return project if project_id == project.id else None

        async def get_dataset(self, dataset_id, _user):
            return source_dataset if dataset_id == source_dataset.id else None

        async def all_dataset_images(self, dataset_id):
            return [source_image] if dataset_id == source_dataset.id else []

    class FakeDatabase:
        def __init__(self):
            self.added = []

        async def scalar(self, _statement):
            return 1

        def add(self, value):
            self.added.append(value)

        async def flush(self):
            for value in self.added:
                if isinstance(value, DatasetVersion) and not value.id:
                    value.id = "dataset-2"

        async def commit(self):
            return None

        async def refresh(self, _value):
            return None

    async def no_refresh(*_args, **_kwargs):
        return None

    monkeypatch.setattr(project_operations, "VisionRepository", FakeRepository)
    application = VisionApplication()
    application._refresh_dataset = no_refresh
    application.dataset_output = lambda dataset: dataset
    db = FakeDatabase()

    created = await application.create_dataset(
        db,
        project.id,
        SimpleNamespace(id=3, org_id=7),
        clone_from_dataset_id=source_dataset.id,
    )

    clone = next(value for value in db.added if isinstance(value, DatasetImage))
    assert created.id == "dataset-2"
    assert clone.storage_uri == source_image.storage_uri
    assert clone.thumbnail_uri == source_image.thumbnail_uri
    assert clone.sha256 == source_image.sha256
    assert clone.split is None
    assert clone.annotation_revision == 0
    assert clone.metadata_json["cloned_from_image_id"] == source_image.id
    assert clone.annotations[0] is not source_image.annotations[0]
    assert clone.annotations[0].class_id == source_image.annotations[0].class_id
