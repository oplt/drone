"""Vision STOR-001: weights register as VisionStorageObject without host paths."""

from __future__ import annotations

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
