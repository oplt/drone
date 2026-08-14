"""Vision STOR-001: weights register as VisionStorageObject without host paths."""

from __future__ import annotations

from backend.modules.vision_models.dataset_models import DatasetImage
from backend.modules.vision_models.service.storage import VisionStorage
from backend.modules.vision_models.training_models import ModelVersion, VisionStorageObject


def test_vision_storage_object_uses_relative_backend_key():
    storage = VisionStorageObject(
        id="so-1",
        checksum="abc123",
        size=128,
        mime="application/octet-stream",
        owner_type="model_version_weights",
        owner_id="mv-1",
        state="final",
        retention_policy="model_artifact",
        backend_key="projects/p1/models/m1/v1/best.pt",
    )
    assert not storage.backend_key.startswith("/")
    assert "://" not in storage.backend_key
    assert storage.state == "final"


def test_model_version_links_storage_object_id():
    assert "storage_object_id" in ModelVersion.__table__.c
    assert ModelVersion.__table__.c.storage_object_id.nullable


def test_dataset_image_links_image_and_thumbnail_storage_objects():
    assert DatasetImage.__table__.c.storage_object_id.nullable
    assert DatasetImage.__table__.c.thumbnail_storage_object_id.nullable


def test_storage_dual_read_prefers_relative_backend_key(tmp_path):
    storage = VisionStorage(tmp_path)
    relative = "projects/p1/datasets/v1/images/image.jpg"
    registered = tmp_path / relative
    registered.parent.mkdir(parents=True)
    registered.write_bytes(b"registered")
    legacy = tmp_path / "legacy.jpg"
    legacy.write_bytes(b"legacy")

    assert storage.resolve_registered(
        backend_key=relative,
        legacy_uri=storage.to_uri(legacy),
    ).read_bytes() == b"registered"
    assert storage.resolve_registered(
        backend_key=None,
        legacy_uri=storage.to_uri(legacy),
    ).read_bytes() == b"legacy"
